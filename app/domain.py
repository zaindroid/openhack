"""Pre-mortem: before a law passes, what went wrong where a similar one already did.

Signal      = a draft law (one per row in `drafts`), scored by how many analogues exist
Hypotheses  = the six risk types evaluation reports document (gaming, cost_overrun, ...)
Skeptic     = counts analogues whose ex-post evaluations reported that risk at medium/high magnitude, and checks
              whether the draft already carries the clause that `features_dict.mitigates` says counters it
Planner     = clauses to add, cost estimate request, pilot/phase — never "pass / don't pass"; the committee decides
Analogue    = same policy_area AND same instrument AND >= 2 shared feature tokens
"""
from __future__ import annotations
from collections import defaultdict
from whycore.domain import Action, Domain, Hypothesis, Signal, TestResult

RISKS = {
    "gaming": "Gaming / fraudulent or strategic claiming",
    "cost_overrun": "Cost overrun against the ex-ante estimate",
    "enforcement_gap": "Enforcement gap: rules on paper, not in practice",
    "equity_harm": "Equity harm: benefits or burdens fall on the wrong groups",
    "take_up_shortfall": "Take-up shortfall: fewer users than planned",
    "unintended_market_effect": "Unintended market effect: prices, exits, substitution",
}
STRONG = ("medium", "high")


def _feats(s) -> set[str]:
    return {t.strip() for t in str(s or "").split(";") if t.strip()}


class PreMortemDomain(Domain):
    name = "pre-mortem"
    title = "Pre-mortem · learn from the laws that came before"
    track = "03"
    question = ("Which risks did evaluation reports document for laws similar to this draft, how often, "
                "and which clauses would mitigate them?")
    description = ("Illustrative corpus of laws and ex-post evaluations (see app/data/seed/README.md). "
                   "Every risk verdict counts analogue laws whose evaluation reports documented it; the draft is "
                   "checked for the clause that counters it. Evidence from analogues, not prediction.")
    views = {
        "drafts": "SELECT draft_id, title, jurisdiction, year, policy_area, instrument, features FROM drafts ORDER BY draft_id",
        "analogues": ("SELECT d.draft_id, d.title AS draft, l.law_id, l.title AS law, l.jurisdiction, l.year, l.features "
                      "FROM drafts d JOIN laws l ON l.policy_area = d.policy_area AND l.instrument = d.instrument "
                      "ORDER BY d.draft_id, l.year"),
        "evaluation_findings": ("SELECT e.eval_id, l.law_id, l.title, l.jurisdiction, e.year, e.body, e.finding_type, e.magnitude, e.summary "
                                "FROM evaluations e JOIN laws l ON l.law_id = e.law_id WHERE e.finding_type <> 'none' "
                                "ORDER BY e.finding_type, e.magnitude DESC"),
        "features_dict": "SELECT feature, meaning, mitigates FROM features_dict ORDER BY feature",
    }
    sources = [
        {"name": "EUR-Lex (EU legislation; REST + SPARQL)", "url": "https://eur-lex.europa.eu", "access": "free, no key", "status": "fetcher app/data/fetch_eurlex.py; seed is illustrative"},
        {"name": "Gesetze im Internet (DE)", "url": "https://www.gesetze-im-internet.de", "access": "free", "status": "manual / scrape"},
        {"name": "Legifrance (FR)", "url": "https://www.legifrance.gouv.fr", "access": "free API with registration", "status": "not wired"},
        {"name": "legislation.gov.uk", "url": "https://www.legislation.gov.uk", "access": "free API", "status": "not wired"},
        {"name": "European Commission ex-post evaluations", "url": "https://commission.europa.eu/law/law-making-process/evaluating-and-improving-existing-laws_en", "access": "free PDFs", "status": "extraction plan in fetch_evaluations.py"},
        {"name": "National audit offices (Bundesrechnungshof, NAO, Cour des comptes, Tribunal de Cuentas, Algemene Rekenkamer)", "url": "https://www.eurosai.org", "access": "free PDFs", "status": "extraction plan in fetch_evaluations.py"},
        {"name": "OECD policy evaluations", "url": "https://www.oecd.org/en/topics/policy-evaluation.html", "access": "free", "status": "not wired"},
    ]

    # ---- helpers -------------------------------------------------------------------------------------------------
    @staticmethod
    def _analogue_sql(draft_id: str) -> str:
        return ("SELECT l.law_id, l.title, l.jurisdiction, l.year, l.features FROM laws l JOIN drafts d "
                f"ON l.policy_area = d.policy_area AND l.instrument = d.instrument WHERE d.draft_id = '{draft_id}' ORDER BY l.year")

    def _analogues(self, draft: dict, data) -> tuple[list[dict], str, int]:
        sql = self._analogue_sql(draft["draft_id"])
        res = data.run_sql(sql)
        df = _feats(draft["features"])
        out = []
        for r in res["rows"]:
            shared = df & _feats(r["features"])
            if len(shared) >= 2:
                out.append({**r, "shared": sorted(shared)})
        return out, sql, res["rows_n"]

    @staticmethod
    def _mitigators(data) -> dict[str, list[str]]:
        res = data.run_sql("SELECT feature, mitigates FROM features_dict WHERE mitigates IS NOT NULL AND mitigates <> ''")
        m = defaultdict(list)
        for r in res["rows"]:
            m[r["mitigates"]].append(r["feature"])
        return m

    # ---- the contract -------------------------------------------------------------------------------------------
    def scout(self, data, limit):
        res = data.run_sql("SELECT * FROM drafts ORDER BY draft_id")
        signals = []
        for d in res["rows"]:
            an, sql, n = self._analogues(d, data)
            juris = sorted({a["jurisdiction"] for a in an})
            signals.append(Signal(
                id=d["draft_id"],
                label=f"Draft: {d['title']} ({len(an)} analogues in {len(juris)} jurisdictions)",
                score=float(len(an)),
                props={**d, "analogues": [a["law_id"] for a in an], "jurisdictions": juris,
                       "memory_key": f"{d['policy_area']}+{d['instrument']}"},
                sql=sql, rows=n))
        return signals[:limit]

    def hypotheses(self, signal, data):
        return [Hypothesis(k, v) for k, v in RISKS.items()]

    def test(self, signal, hyp, data):
        risk = hyp.id
        ids = signal.props.get("analogues", [])
        if not ids:
            return TestResult(risk, "uncertain", "no analogue laws found (same area, instrument, >=2 shared features)")
        id_list = ", ".join(f"'{i}'" for i in ids)
        sql = ("SELECT e.law_id, l.jurisdiction, l.year, e.finding_type, e.magnitude, e.eval_id, e.url "
               f"FROM evaluations e JOIN laws l ON l.law_id = e.law_id WHERE e.law_id IN ({id_list}) ORDER BY l.year")
        res = data.run_sql(sql)
        evaluated = {r["law_id"] for r in res["rows"]}
        hits = {}
        for r in res["rows"]:
            if r["finding_type"] == risk and r["magnitude"] in STRONG:
                hits.setdefault(r["law_id"], r)
        draft_feats = _feats(signal.props.get("features"))
        mit = self._mitigators(data).get(risk, [])
        present = sorted(draft_feats & set(mit))
        hit_desc = ", ".join(f"{h['jurisdiction']} {h['year']}" for h in hits.values())
        data_out = {"analogues": len(ids), "evaluated": len(evaluated), "hits": len(hits), "hit_laws": list(hits),
                    "eval_ids": [h["eval_id"] for h in hits.values()], "urls": [h["url"] for h in hits.values()],
                    "mitigators": mit, "present_in_draft": present}
        if len(evaluated) < 2:
            return TestResult(risk, "uncertain", f"only {len(evaluated)} of {len(ids)} analogues have an ex-post evaluation; too few to judge",
                              sql, res["rows_n"], data_out)
        if present:
            return TestResult(risk, "reject",
                              f"{len(hits)} of {len(evaluated)} evaluated analogues reported it{' (' + hit_desc + ')' if hits else ''}, "
                              f"but the draft already contains {', '.join(present)}, the clause that counters it",
                              sql, res["rows_n"], data_out)
        if len(hits) >= 2:
            return TestResult(risk, "support",
                              f"{len(hits)} of {len(evaluated)} evaluated analogues ({hit_desc}) reported {risk.replace('_', ' ')} at medium/high; "
                              f"the draft has no {' / '.join(mit) if mit else 'countermeasure'} clause",
                              sql, res["rows_n"], data_out)
        if len(evaluated) >= 3 and not hits:
            return TestResult(risk, "reject", f"none of {len(evaluated)} evaluated analogues reported {risk.replace('_', ' ')} at medium/high",
                              sql, res["rows_n"], data_out)
        return TestResult(risk, "uncertain", f"{len(hits)} of {len(evaluated)} evaluated analogues reported it ({hit_desc}); one case is not a pattern",
                          sql, res["rows_n"], data_out)

    def plan(self, signal, verdicts, data):
        acts: list[Action] = []
        supported = [v for v in verdicts if v.verdict == "support"]
        supported.sort(key=lambda v: -v.data.get("hits", 0))
        title = signal.props.get("title", signal.id)
        p = 1
        for v in supported:
            mit = v.data.get("mitigators") or []
            clause = " or ".join(m.replace("_", " ") for m in mit) if mit else "a countermeasure"
            acts.append(Action(f"{signal.id}-{v.hypothesis_id}",
                               f"Add clause: {clause} (counters {v.hypothesis_id.replace('_', ' ')}, seen in {v.data.get('hits')} analogues)",
                               p, v.reason,
                               {"evidence": v.data.get("eval_ids", []), "urls": v.data.get("urls", []), "risk": v.hypothesis_id}))
            p += 1
            if v.hypothesis_id == "cost_overrun":
                acts.append(Action(f"{signal.id}-cost-estimate", f"Request an ex-ante cost estimate for {title} benchmarked on analogue overruns",
                                   p, "analogue evaluations documented cost overruns; the estimate should cite them",
                                   {"evidence": v.data.get("eval_ids", [])}))
                p += 1
            if v.hypothesis_id == "take_up_shortfall":
                acts.append(Action(f"{signal.id}-pilot", f"Pilot or phase the rollout of {title} with review gates",
                                   p, "analogues with low take-up had no phased rollout or outreach", {"evidence": v.data.get("eval_ids", [])}))
                p += 1
        if not supported:
            unc = [v for v in verdicts if v.verdict == "uncertain"]
            if unc:
                acts.append(Action(f"{signal.id}-widen", f"Widen the analogue search for {title} (other jurisdictions, adjacent instruments)",
                                   1, f"{len(unc)} risks could not be judged: too few evaluated analogues"))
            else:
                acts.append(Action(f"{signal.id}-note", f"Record: no documented analogue risk for {title}", 1,
                                   "all risk types rejected on the evidence; keep monitoring after adoption"))
        return acts

    def explain_prompt(self, signal, verdicts, actions):
        sys_ = ("You brief a parliamentary committee on a draft law using only the analogue evidence below. Plain language, "
                "at most 140 words. State how many analogues were evaluated, which risks they documented and which the draft "
                "already mitigates. Never recommend passing or rejecting the law; the committee decides. Use only numbers present in the input.")
        lines = [f"Draft: {signal.props.get('title')} ({signal.props.get('jurisdiction')}, {signal.props.get('instrument')}, "
                 f"{signal.props.get('policy_area')}); analogues: {len(signal.props.get('analogues', []))} in {', '.join(signal.props.get('jurisdictions', []))}"]
        for v in verdicts:
            lines.append(f"- {v.hypothesis_id}: {v.verdict.upper()} — {v.reason}")
        lines.append("Suggested clauses (drafts): " + "; ".join(f"{a.priority}. {a.label}" for a in actions))
        return sys_, "\n".join(lines)


DOMAIN = PreMortemDomain()
