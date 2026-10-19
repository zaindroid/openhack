"""Lazarus — the rediscovery engine.

Signal      = an open problem (table `problems`).
Hypothesis  = a candidate "bridge" paper from a DIFFERENT parent field that shares entities with the problem.
Skeptic     = a bridge is supported only if all three hold, each proven by a query:
              (1) ≥2 shared entities are methods or mechanisms, not generic words      (table entity_kinds)
              (2) no citation path from the problem's field to the paper within 2 hops   (table citations)
              (3) the paper is ≥5 years older than the problem                           (older solution, forgotten)
Planner     = read-and-map action, a structured rediscovery brief, a validation contact; or widen the search.
The model explains the verdicts; it never decides them.
"""
from __future__ import annotations
from whycore.domain import Action, Domain, Hypothesis, Signal, TestResult

MIN_METHOD_OVERLAP = 2
MIN_GAP_YEARS = 5
MAX_HOPS = 2


def q(s: str) -> str:
    return s.replace("'", "''")


class LazarusDomain(Domain):
    name = "lazarus"
    title = "Lazarus · rediscovery engine"
    track = "02"
    question = "Which solved problems in other fields answer this open problem, and is the bridge real?"
    description = ("Illustrative corpus (see app/data/seed/README.md); run app/data/fetch_openalex.py for real literature. "
                   "A bridge counts only when shared entities are methods or mechanisms, no citation path exists within two hops, "
                   "and the solution is at least five years older than the problem.")
    views = {
        "problems": "SELECT problem_id, title, field, year, key_entities FROM problems ORDER BY year DESC",
        "papers_by_field": "SELECT f.parent_field, p.field, p.paper_id, p.year, p.title, p.cited_by_count FROM papers p JOIN fields f ON f.field = p.field ORDER BY f.parent_field, p.field, p.year",
        "entity_kinds": "SELECT kind, entity FROM entity_kinds ORDER BY kind, entity",
        "citations": "SELECT citing_id, cited_id FROM citations ORDER BY citing_id",
    }
    sources = [
        {"name": "OpenAlex (works, concepts, referenced_works; 250 M works)", "url": "https://docs.openalex.org", "access": "REST API, free, polite-pool email; full snapshot free on S3 (s3://openalex)", "status": "fetcher written, not yet run"},
        {"name": "Semantic Scholar Academic Graph", "url": "https://api.semanticscholar.org", "access": "REST API, free key", "status": "optional second source"},
        {"name": "Crossref", "url": "https://api.crossref.org", "access": "REST API, free", "status": "optional, metadata only"},
        {"name": "Seed corpus", "url": "", "access": "app/data/seed/*.csv", "status": "ILLUSTRATIVE — invented papers for offline tests"},
    ]

    # ---- Scout -----------------------------------------------------------------------------------------------
    def scout(self, data, limit):
        sql = (
            "SELECT q.problem_id, q.title, q.field, q.year, q.statement, q.key_entities, fq.parent_field, "
            "(SELECT COUNT(DISTINCT p.paper_id) FROM problem_entities qe "
            " JOIN entity_kinds k ON k.entity = qe.entity AND k.kind IN ('method','mechanism') "
            " JOIN paper_entities pe ON pe.entity = qe.entity "
            " JOIN papers p ON p.paper_id = pe.paper_id JOIN fields fp ON fp.field = p.field "
            " WHERE qe.problem_id = q.problem_id AND fp.parent_field <> fq.parent_field) AS candidates "
            "FROM problems q JOIN fields fq ON fq.field = q.field ORDER BY candidates DESC, q.year DESC"
        )
        res = data.run_sql(sql)
        out = []
        for r in res["rows"][:limit]:
            props = dict(r); props["memory_key"] = r["problem_id"]
            out.append(Signal(id=r["problem_id"], label=f"{r['title']} ({r['field']}, {r['year']})",
                              score=float(r["candidates"] or 0), props=props, sql=sql, rows=res["rows_n"]))
        return out

    # ---- Investigator ----------------------------------------------------------------------------------------
    def hypotheses(self, signal, data):
        pid, field = q(signal.id), q(signal.props["field"])
        sql = (
            "SELECT p.paper_id, p.title, p.field, p.year, COUNT(*) AS shared "
            "FROM papers p JOIN fields f ON f.field = p.field "
            "JOIN paper_entities pe ON pe.paper_id = p.paper_id "
            f"JOIN problem_entities qe ON qe.entity = pe.entity AND qe.problem_id = '{pid}' "
            f"WHERE f.parent_field <> (SELECT f2.parent_field FROM fields f2 WHERE f2.field = '{field}') "
            "GROUP BY p.paper_id, p.title, p.field, p.year ORDER BY shared DESC, p.year ASC LIMIT 4"
        )
        res = data.run_sql(sql)
        return [Hypothesis(id=r["paper_id"], label=f"{r['title']} ({r['field']}, {r['year']})",
                           props={"field": r["field"], "year": int(r["year"]), "shared": int(r["shared"]), "sql": sql})
                for r in res["rows"]]

    # ---- Skeptic ---------------------------------------------------------------------------------------------
    def test(self, signal, hyp, data):
        pid, field, paper = q(signal.id), q(signal.props["field"]), q(hyp.id)
        # (1) kind of overlap
        sql1 = (
            "SELECT k.kind, COUNT(*) AS n FROM paper_entities pe "
            f"JOIN problem_entities qe ON qe.entity = pe.entity AND qe.problem_id = '{pid}' "
            f"JOIN entity_kinds k ON k.entity = pe.entity WHERE pe.paper_id = '{paper}' GROUP BY k.kind"
        )
        r1 = data.run_sql(sql1)
        kinds = {r["kind"]: int(r["n"]) for r in r1["rows"]}
        n_method = kinds.get("method", 0) + kinds.get("mechanism", 0)
        n_generic = kinds.get("generic", 0)
        if not kinds:
            return TestResult(hyp.id, "uncertain", "no classified shared entities (entity_kinds has no row for them)", sql1, r1["rows_n"], {"kinds": kinds})
        if n_method < MIN_METHOD_OVERLAP:
            return TestResult(hyp.id, "reject",
                              f"only {n_method} shared method/mechanism entities ({n_generic} generic, {kinds.get('object', 0)} object); need {MIN_METHOD_OVERLAP}",
                              sql1, r1["rows_n"], {"kinds": kinds})
        # (2) citation path within MAX_HOPS from the problem's field
        sql2 = (
            "SELECT MIN(hops) AS hops FROM ("
            f" SELECT 1 AS hops FROM citations c JOIN papers a ON a.paper_id = c.citing_id WHERE a.field = '{field}' AND c.cited_id = '{paper}'"
            " UNION ALL "
            f" SELECT 2 AS hops FROM citations c1 JOIN papers a ON a.paper_id = c1.citing_id "
            f" JOIN citations c2 ON c2.citing_id = c1.cited_id WHERE a.field = '{field}' AND c2.cited_id = '{paper}'"
            ") t"
        )
        r2 = data.run_sql(sql2)
        hops = r2["rows"][0]["hops"] if r2["rows"] else None
        if hops is not None:
            return TestResult(hyp.id, "reject", f"already connected: citation path of length {int(hops)} from {signal.props['field']} to this paper",
                              sql2, r2["rows_n"], {"hops": int(hops), "kinds": kinds})
        # (3) time gap
        sql3 = f"SELECT (SELECT year FROM problems WHERE problem_id = '{pid}') - (SELECT year FROM papers WHERE paper_id = '{paper}') AS gap_years"
        r3 = data.run_sql(sql3)
        gap = int(r3["rows"][0]["gap_years"])
        if gap < MIN_GAP_YEARS:
            return TestResult(hyp.id, "reject", f"only {gap} years older than the problem; a rediscovery needs ≥{MIN_GAP_YEARS} (this is contemporary work, not forgotten work)",
                              sql3, r3["rows_n"], {"gap_years": gap, "kinds": kinds})
        combined = sql1 + ";\n" + sql2 + ";\n" + sql3
        return TestResult(hyp.id, "support",
                          f"{n_method} shared method/mechanism entities, no citation path within {MAX_HOPS} hops from {signal.props['field']}, {gap} years older",
                          combined, r1["rows_n"] + r2["rows_n"] + r3["rows_n"], {"kinds": kinds, "hops": None, "gap_years": gap})

    # ---- Planner ---------------------------------------------------------------------------------------------
    def plan(self, signal, verdicts, data):
        supported = [v for v in verdicts if v.verdict == "support"]
        supported.sort(key=lambda v: -(v.data.get("kinds", {}).get("method", 0) + v.data.get("kinds", {}).get("mechanism", 0)))
        pid = signal.id
        if not supported:
            return [Action(f"{pid}-widen", f"Widen the search for '{signal.props['title']}' to adjacent fields and older decades", 1,
                           "no candidate passed all three tests: " + "; ".join(f"{v.hypothesis_id}: {v.reason}" for v in verdicts)[:400],
                           {"rejected": [v.hypothesis_id for v in verdicts]})]
        best = supported[0]
        paper = data.run_sql(f"SELECT paper_id, title, field, year, abstract FROM papers WHERE paper_id = '{q(best.hypothesis_id)}'")["rows"][0]
        shared = data.run_sql(
            "SELECT pe.entity, k.kind FROM paper_entities pe JOIN problem_entities qe ON qe.entity = pe.entity "
            f"AND qe.problem_id = '{q(pid)}' JOIN entity_kinds k ON k.entity = pe.entity WHERE pe.paper_id = '{q(paper['paper_id'])}' "
            "AND k.kind IN ('method','mechanism') ORDER BY k.kind, pe.entity")["rows"]
        brief = {
            "problem": {"id": pid, "title": signal.props["title"], "field": signal.props["field"], "year": signal.props["year"]},
            "bridge_paper": {"id": paper["paper_id"], "title": paper["title"], "field": paper["field"], "year": paper["year"]},
            "shared_mechanisms": [f"{s['entity']} ({s['kind']})" for s in shared],
            "gap_years": best.data.get("gap_years"),
            "why_uncited": f"no citation path from {signal.props['field']} within {MAX_HOPS} hops; different parent field",
            "status": "candidate for expert review — not a claim of novelty",
        }
        acts = [
            Action(f"{pid}-read", f"Read '{paper['title']}' ({paper['field']}, {paper['year']}) and map its method onto '{signal.props['title']}'", 1,
                   best.reason, {"paper_id": paper["paper_id"]}),
            Action(f"{pid}-brief", "Draft rediscovery brief for the team", 2, "structured brief in props.brief; a human expert decides whether the bridge holds", {"brief": brief}),
            Action(f"{pid}-contact", f"Contact the {paper['field']} community / authors to validate the mapping", 3, "validation before any claim is made", {}),
        ]
        for v in supported[1:]:
            acts.append(Action(f"{pid}-alt-{v.hypothesis_id}", f"Also read {v.hypothesis_id} (second supported bridge)", 4, v.reason, {}))
        return acts

    def explain_prompt(self, signal, verdicts, actions):
        sys_ = ("You explain literature bridges to a researcher in plain language, at most 120 words. Use only the facts given. "
                "Name the supported paper, say which two tests the rejected ones failed, and end with the first action. Never claim novelty; say 'candidate'.")
        lines = [f"Open problem: {signal.label}", f"Statement: {signal.props.get('statement', '')}"]
        for v in verdicts:
            lines.append(f"- candidate {v.hypothesis_id}: {v.verdict.upper()} — {v.reason}")
        lines.append("Actions: " + "; ".join(f"{a.priority}. {a.label}" for a in actions))
        return sys_, "\n".join(lines)

    def extra_json(self, data):
        return {"center": [50, 10], "zoom": 3, "note": "no geography in this domain; map stays empty"}


DOMAIN = LazarusDomain()
