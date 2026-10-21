"""The agent loop. Deterministic where it matters; the model explains at the end.

run(question) →
  Scout       : domain.scout()                          → signals (each with its SQL)
  Investigator: domain.hypotheses(signal)               → ≥2 competing causes; recalled rejections are skipped (warm run)
  Skeptic     : domain.test(signal, hypothesis)         → support | reject | uncertain, with the SQL as written and as
                                                          executed + rows; signals run TEST_CONCURRENCY at a time
                'nothing rejected' is logged as a failure state (rule 4), never hidden
  Planner     : domain.plan(signal, verdicts)           → ranked draft actions
  Explainer   : model.chat(domain.explain_prompt(...))  → prose for humans (offline templater without a key)
  Memory      : rejections remembered per signal fingerprint
"""
from __future__ import annotations
import time, uuid
from concurrent.futures import ThreadPoolExecutor, wait
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
        self.extras: dict = {}            # filled by run hooks (e.g. a signed attestation)

    # ------------------------------------------------------------------------------------------------------------
    def execute(self) -> "Run":
        L, D = self.ledger, self.domain
        self.status = "running"
        L.step("scout", "finding signals", backend=data.mode)
        signals = D.scout(data, self.max_signals)
        signals.sort(key=lambda s: -s.score)
        signals = signals[: self.max_signals]
        L.step("scout", f"{len(signals)} signals")
        # Signals are independent: their hypotheses and tests run TEST_CONCURRENCY at a time. Each worker returns its
        # claims and steps, which go into the ledger in signal order, so the ledger (and its signature) do not depend
        # on thread timing.
        with ThreadPoolExecutor(max_workers=max(1, settings.test_concurrency)) as ex:
            done = list(ex.map(self._signal, signals))
        prompts: list[tuple[str, str]] = []
        for out in done:
            for c in out["claims"]:
                L.add(c)
            L.steps.extend(out["steps"])
            self.failures.extend(out["failures"])
            self.tests_run += out["tests_run"]
            self.skipped_by_memory += out["skipped"]
            prompts.append(out["prompt"])
            self.results.append(out["result"])
        # Hooks marked `explanation_free` read verdicts and actions only (the World Model, the run brief), so they run
        # while the Explainer waits on the model; the others (the Notary signs the explanations) run after it.
        early, late = self._hooks()
        bg = ThreadPoolExecutor(max_workers=len(early)) if early else None
        futs = [bg.submit(self._hook, spec, fn) for spec, fn in early] if bg else []
        self._explain(prompts)
        for f in futs:
            f.result()
        if bg:
            bg.shutdown()
        self.status = "done"
        memory.log_run(self.summary())
        for spec, fn in late:
            self._hook(spec, fn)
        return self

    def _signal(self, s) -> dict:
        """Investigator, Skeptic and Planner for one signal; returns its claims and steps instead of writing them."""
        D, t0 = self.domain, self.ledger.t0
        claims, steps, failures = [], [], []
        step = lambda agent, what, **kw: steps.append({"t": round(time.time() - t0, 3), "agent": agent, "what": what, **kw})
        s.sql_executed = s.sql_executed or data.executed(s.sql)
        claims.append(Claim(text=s.label, kind="signal", sql=s.sql, sql_executed=s.sql_executed, source=data.mode, rows=s.rows, data=s.props))
        fp = memory.fingerprint(D.name, s.id, s.props)
        known = memory.recall(fp)
        hyps = D.hypotheses(s, data)
        if len(hyps) < 2:
            failures.append(f"{s.id}: fewer than 2 competing hypotheses (rule 4)")
        step("investigator", "hypotheses", signal=s.id, n=len(hyps), remembered_rejections=len(known))
        verdicts: list[TestResult] = []
        tests_run = skipped = 0
        for h in hyps:
            if h.id in known:
                verdicts.append(TestResult(h.id, "reject", f"remembered from an earlier run: {known[h.id]}", sql=None))
                skipped += 1
                step("memory", "skipped hypothesis", signal=s.id, hypothesis=h.id)
                continue
            try:
                v = D.test(s, h, data)
            except Exception as e:  # a broken test is an uncertain verdict with the error, never a crash
                v = TestResult(h.id, "uncertain", f"test failed: {str(e)[:140]}")
            v.sql_executed = v.sql_executed or data.executed(v.sql)
            tests_run += 1
            verdicts.append(v)
            claims.append(Claim(text=f"{h.label}: {v.reason}", kind="test", sql=v.sql, sql_executed=v.sql_executed, source=data.mode,
                                rows=v.rows, data=v.data,
                                status={"support": "supported", "reject": "rejected", "uncertain": "uncertain"}[v.verdict]))
            step("skeptic", v.verdict, signal=s.id, hypothesis=h.id)
        if hyps and not any(v.verdict == "reject" for v in verdicts):
            failures.append(f"{s.id}: Skeptic could not reject any hypothesis (rule 4 failure state)")
        memory.remember(fp, {v.hypothesis_id: v.reason for v in verdicts if v.verdict == "reject" and v.sql})
        actions = D.plan(s, verdicts, data)
        actions.sort(key=lambda a: a.priority)
        for a in actions:
            claims.append(Claim(text=a.label, kind="action", sql=None, status="unverified", data={"priority": a.priority, "rationale": a.rationale}))
        result = {"signal": asdict(s), "hypotheses": [asdict(h) for h in hyps], "verdicts": [asdict(v) for v in verdicts],
                  "supported": [v.hypothesis_id for v in verdicts if v.verdict == "support"], "actions": [asdict(a) for a in actions],
                  "explanation": ""}
        return {"claims": claims, "steps": steps, "failures": failures, "tests_run": tests_run, "skipped": skipped,
                "prompt": D.explain_prompt(s, verdicts, actions), "result": result}

    def _explain(self, prompts: list[tuple[str, str]]) -> None:
        """Explainer: one model call per signal, MODEL_CONCURRENCY at a time (a 50-asset run must finish well inside the
        edge's 100 s). Each explanation records the route, host and model that produced it (or the cache hit). A failed
        call is labelled as such in the UI and the ledger, never replaced by invented text."""
        def one(p: tuple[str, str]) -> tuple[str, dict]:
            try:
                return model.answer(p[0], p[1], deep=True)
            except Exception as e:
                return f"[model error] {str(e)[:200]}", {"model": model.ep["reason"].model, "route": model.ep["reason"].route, "ok": False}
        # The whole step gets EXPLAIN_BUDGET_S; calls still running then are labelled pending and left to finish in the
        # background, where they fill the explanation cache, so the next run on the same evidence shows them.
        # Identical prompts (same evidence, e.g. two certificates with the same facts) are sent once.
        ex = ThreadPoolExecutor(max_workers=max(1, settings.model_concurrency))
        uniq = {p: ex.submit(one, p) for p in dict.fromkeys(prompts)}
        wait(list(uniq.values()), timeout=settings.explain_budget_s)
        ex.shutdown(wait=False)
        pending = {"model": model.ep["reason"].model, "route": model.ep["reason"].route, "ok": False, "pending": True}
        outs = [uniq[p].result() if uniq[p].done() else (f"[model pending] not answered within the {settings.explain_budget_s:g} s "
                                                          "explanation budget; it is still being generated and will come from the cache on the next run", pending)
                for p in prompts]
        for r, (text, meta) in zip(self.results, outs):
            r["explanation"] = text
            r["explanation_model"] = meta
            self.ledger.add(Claim(text=text, kind="explanation", status="unverified", data=meta))
            self.ledger.step("explainer", "done" if meta["ok"] else "failed", signal=r["signal"]["id"], model=meta["model"])

    def _hooks(self) -> tuple[list, list]:
        """RUN_HOOKS split into (explanation_free, the rest), each as [(spec, callable or its import error)]."""
        import importlib
        early, late = [], []
        for spec in [h.strip() for h in settings.run_hooks.split(",") if h.strip()]:
            mod, _, fn = spec.partition(":")
            try:
                f = getattr(importlib.import_module(mod), fn or "run_hook")
            except Exception as e:
                late.append((spec, e)); continue
            (early if getattr(f, "explanation_free", False) else late).append((spec, f))
        return early, late

    def _hook(self, spec: str, fn) -> None:
        try:
            if isinstance(fn, Exception):
                raise fn
            fn(self)
            self.ledger.step("hook", spec)
        except Exception as e:  # a hook must never break a run; record and continue
            self.ledger.step("hook", f"{spec} failed: {str(e)[:160]}")

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
        return {"summary": self.summary(), "status": self.status, "results": self.results, "ledger": self.ledger.to_dict(), "extras": self.extras,
                "domain": {"name": self.domain.name, "title": self.domain.title, "track": self.domain.track,
                           "question": self.domain.question, "description": self.domain.description}}
