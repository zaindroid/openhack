"""The agent loop. Deterministic where it matters; the model explains at the end.

run(question) →
  Scout       : domain.scout()                          → signals (each with its SQL)
  Investigator: domain.hypotheses(signal)               → ≥2 competing causes; recalled rejections are skipped (warm run)
  Skeptic     : domain.test(signal, hypothesis)         → support | reject | uncertain, with SQL + rows
                'nothing rejected' is logged as a failure state (rule 4), never hidden
  Planner     : domain.plan(signal, verdicts)           → ranked draft actions
  Explainer   : model.chat(domain.explain_prompt(...))  → prose for humans (offline templater without a key)
  Memory      : rejections remembered per signal fingerprint
"""
from __future__ import annotations
import time, uuid
from dataclasses import asdict
from whycore.data import data
from whycore.domain import Domain, TestResult
from whycore.ledger import Claim, Ledger
from whycore.memory import memory
from whycore.model import model
from whycore.settings import settings


class Run:
    def __init__(self, domain: Domain, question: str | None = None, max_signals: int | None = None) -> None:
        self.id = uuid.uuid4().hex[:8]
        self.domain = domain
        self.question = question or domain.question
        self.max_signals = max_signals or settings.max_signals
        self.ledger = Ledger()
        self.results: list[dict] = []
        self.failures: list[str] = []
        self.skipped_by_memory = 0
        self.tests_run = 0
        self.created = time.time()
        self.status = "created"

    # ------------------------------------------------------------------------------------------------------------
    def execute(self) -> "Run":
        L, D = self.ledger, self.domain
        self.status = "running"
        L.step("scout", "finding signals", backend=data.mode)
        signals = D.scout(data, self.max_signals)
        signals.sort(key=lambda s: -s.score)
        for s in signals[: self.max_signals]:
            L.add(Claim(text=s.label, kind="signal", sql=s.sql, source=data.mode, rows=s.rows, data=s.props))
            fp = memory.fingerprint(D.name, s.id, s.props)
            known = memory.recall(fp)
            hyps = D.hypotheses(s, data)
            if len(hyps) < 2:
                self.failures.append(f"{s.id}: fewer than 2 competing hypotheses (rule 4)")
            L.step("investigator", "hypotheses", signal=s.id, n=len(hyps), remembered_rejections=len(known))
            verdicts: list[TestResult] = []
            for h in hyps:
                if h.id in known:
                    verdicts.append(TestResult(h.id, "reject", f"remembered from an earlier run: {known[h.id]}", sql=None))
                    self.skipped_by_memory += 1
                    L.step("memory", "skipped hypothesis", signal=s.id, hypothesis=h.id)
                    continue
                try:
                    v = D.test(s, h, data)
                except Exception as e:  # a broken test is an uncertain verdict with the error, never a crash
                    v = TestResult(h.id, "uncertain", f"test failed: {str(e)[:140]}")
                self.tests_run += 1
                verdicts.append(v)
                L.add(Claim(text=f"{h.label}: {v.reason}", kind="test", sql=v.sql, source=data.mode, rows=v.rows,
                            data=v.data, status={"support": "supported", "reject": "rejected", "uncertain": "uncertain"}[v.verdict]))
                L.step("skeptic", v.verdict, signal=s.id, hypothesis=h.id)
            if hyps and not any(v.verdict == "reject" for v in verdicts):
                self.failures.append(f"{s.id}: Skeptic could not reject any hypothesis (rule 4 failure state)")
            memory.remember(fp, {v.hypothesis_id: v.reason for v in verdicts if v.verdict == "reject" and v.sql})
            actions = D.plan(s, verdicts, data)
            actions.sort(key=lambda a: a.priority)
            for a in actions:
                L.add(Claim(text=a.label, kind="action", sql=None, status="unverified", data={"priority": a.priority, "rationale": a.rationale}))
            sys_, user = D.explain_prompt(s, verdicts, actions)
            explanation = model.chat(sys_, user, deep=True)
            L.add(Claim(text=explanation, kind="explanation", status="unverified"))
            L.step("explainer", "done", signal=s.id, model_online=model.online)
            self.results.append({
                "signal": asdict(s),
                "hypotheses": [asdict(h) for h in hyps],
                "verdicts": [asdict(v) for v in verdicts],
                "supported": [v.hypothesis_id for v in verdicts if v.verdict == "support"],
                "actions": [asdict(a) for a in actions],
                "explanation": explanation,
            })
        self.status = "done"
        memory.log_run(self.summary())
        return self

    # ------------------------------------------------------------------------------------------------------------
    def approve(self, action_id: str, approve: bool = True) -> dict | None:
        for r in self.results:
            for a in r["actions"]:
                if a["id"] == action_id:
                    a["status"] = "approved" if approve else "rejected"
                    self.ledger.step("human", a["status"], action=action_id)
                    return a
        return None

    def summary(self) -> dict:
        return {"run_id": self.id, "domain": self.domain.name, "question": self.question, "signals": len(self.results),
                "tests_run": self.tests_run, "skipped_by_memory": self.skipped_by_memory, "warm": self.skipped_by_memory > 0,
                "failures": self.failures, "provenance_pct": self.ledger.provenance_pct(), "model": model.status(),
                "data_backend": data.mode, "elapsed_s": round(time.time() - self.created, 2)}

    def to_dict(self) -> dict:
        return {"summary": self.summary(), "status": self.status, "results": self.results, "ledger": self.ledger.to_dict(),
                "domain": {"name": self.domain.name, "title": self.domain.title, "track": self.domain.track,
                           "question": self.domain.question, "description": self.domain.description}}
