"""Exposure. Deterministic SQL only: which policies and sites sit inside the mapped flood footprint (exposure_join,
in_footprint = 1), the sum insured, and the split by segment. Adds the site -> exposure hypothesis with number claims the
Judge can check exactly. The contract view has no customer column yet; customer_id is carried in the state for the UI.

Owner: Ayush and Zain (v0.6.0).
"""
from __future__ import annotations
import re, time
from floodsense_agents.models import Claim, ExposedAsset, Exposure, Hypothesis
from floodsense_agents.nodes.investigator import cite
from floodsense_agents.settings import settings
from floodsense_agents.state import Deps, FloodState, add_evidence, trace


def make(deps: Deps):
    def exposure(state: FloodState) -> dict:
        t = time.time()
        s = settings.schema
        q = deps.zetaris.run_sql(f"SELECT policy_id, site_id, lat, lon, segment, sum_insured_eur FROM {s}.exposure_join WHERE in_footprint = 1 ORDER BY sum_insured_eur DESC")
        agg = deps.zetaris.run_sql(f"SELECT segment, COUNT(*) AS policies, SUM(sum_insured_eur) AS sum_insured_eur FROM {s}.exposure_join WHERE in_footprint = 1 "
                                   f"GROUP BY segment ORDER BY sum_insured_eur DESC")
        assets = [ExposedAsset(**r) for r in q.rows_sample]
        total = sum(a.sum_insured_eur or 0 for a in assets)
        exp = Exposure(assets=assets, policies=q.row_count, sum_insured_eur=total, by_segment=agg.rows_sample, query_ids=[q.query_id, agg.query_id])

        claims = [Claim(**c) for c in state["claims"]]
        n = max([int(m.group(1)) for c in claims if (m := re.match(r"C(\d+)$", c.claim_id))] or [0])
        prov = state.get("provenance", [])
        new_ids: list[str] = []
        if assets:
            n += 1; cid = f"C{n}"
            claims.append(Claim(claim_id=cid, kind="number", hypothesis_id="H4", citations=cite(cid, q, prov, 1), numbers=[q.row_count, total],
                                text=f"{q.row_count} policies sit inside the mapped footprint, sum insured {total:,.0f} EUR; the largest is {assets[0].policy_id} "
                                     f"({assets[0].segment}, {assets[0].sum_insured_eur:,.0f} EUR)."))
            new_ids.append(cid)
            if agg.rows_sample:
                top = agg.rows_sample[0]
                n += 1; cid = f"C{n}"
                claims.append(Claim(claim_id=cid, kind="number", hypothesis_id="H4", citations=cite(cid, agg, prov, 1), numbers=[top["policies"], top["sum_insured_eur"]],
                                    text=f"The most exposed segment is {top['segment']}: {top['policies']} policies, {top['sum_insured_eur']:,.0f} EUR sum insured."))
                new_ids.append(cid)
        hyps = [Hypothesis(**h) for h in state["hypotheses"] if h["id"] != "H4"]
        hyps.append(Hypothesis(id="H4", link="site->exposure", citations=new_ids, status="supported" if assets else "not_supported", rounds=0,
                               evidence=[q.query_id], statement=f"{len(assets)} insured sites are exposed" if assets else "No insured site in the footprint",
                               rationale="deterministic join on exposure_join.in_footprint = 1"))
        return {"exposure": exp.model_dump(), "claims": [c.model_dump() for c in claims], "hypotheses": [h.model_dump() for h in hyps],
                "evidence": add_evidence(state, q, agg),
                "trace": trace(state, "exposure", f"{len(assets)} exposed policies, {total:,.0f} EUR sum insured, {len(new_ids)} new number claims", lane="sql",
                               started=t, evidence_ids=[q.query_id, agg.query_id])}
    return exposure
