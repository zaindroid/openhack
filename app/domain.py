"""Maintenance Debt — which bridge or dam fails first in a region, why, and which repair prevents the most harm.

Signals   : assets past design life, in NBI 'poor' condition (any rating <= 4), dams in poor/unsatisfactory condition or
            high-hazard dams without an emergency action plan. Scored by harm = exposure x condition deficit.
Hypotheses: bridges  age_past_design_life | scour_flood_exposure | deferred_inspection | overload_traffic_growth
            dams     age | hazard_without_eap | deferred_inspection | flood_exposure
Tests     : deterministic SQL against the inventory tables; every verdict carries its query and row count.
Plan      : ranked repair / inspection drafts, plus a region-level maintenance-debt estimate (illustrative cost column).

Ratings are the inspector's (NBI items 58/59/60), never ours. This is a ranking aid for engineers.
"""
from __future__ import annotations
import os
from datetime import date
from whycore.domain import Action, Domain, Hypothesis, Signal, TestResult

AS_OF = date.fromisoformat(os.environ.get("AS_OF", "2026-10-20"))
DAM_DESIGN_LIFE = 50            # nominal; NID has no design-life field
DAM_INTERVAL_MONTHS = {"high": 12, "significant": 24, "low": 60}
CONDITION_DEFICIT = {"unsatisfactory": 4, "poor": 3, "fair": 1, "satisfactory": 0}


def _months_between(a: date, b: date) -> int:
    return (b.year - a.year) * 12 + (b.month - a.month)


def _b(v) -> bool:
    return str(v).strip().lower() in ("true", "1", "t", "yes", "y")


class MaintenanceDebtDomain(Domain):
    name = "maintenance-debt"
    title = "Maintenance Debt · which asset fails first"
    track = "03"
    question = "Which bridges and dams in this region are past their design life, why are they deteriorating, and which repairs prevent the most harm first?"
    description = ("Illustrative inventory for the Pittsburgh area (names, ratings and dates invented). Run app/data/fetch_nbi.py, fetch_nid.py and "
                   "fetch_fema_floods.py for real state data. Ratings follow the NBI 0-9 scale; <= 4 is 'poor'.")
    views = {
        "worst_bridges": ("SELECT structure_id, name, county, year_built, year_reconstructed, design_life_years, deck_rating, superstructure_rating, "
                          "substructure_rating, scour_critical, adt, last_inspection, posted_load_limit FROM bridges "
                          "ORDER BY LEAST(deck_rating, superstructure_rating, substructure_rating), adt DESC"),
        "worst_dams": ("SELECT dam_id, name, year_completed, hazard_class, condition, last_inspection, population_downstream, eap_present FROM dams "
                       "ORDER BY CASE condition WHEN 'unsatisfactory' THEN 0 WHEN 'poor' THEN 1 WHEN 'fair' THEN 2 ELSE 3 END, population_downstream DESC"),
        "region_summary": ("SELECT county, COUNT(*) AS bridges, SUM(CASE WHEN LEAST(deck_rating, superstructure_rating, substructure_rating) <= 4 THEN 1 ELSE 0 END) AS poor, "
                           "SUM(adt) AS total_adt, SUM(replacement_cost_usd) AS replacement_cost_usd FROM bridges GROUP BY county ORDER BY poor DESC"),
        "floods": "SELECT county, year, events FROM floods ORDER BY county, year",
    }
    sources = [
        {"name": "FHWA National Bridge Inventory (per-state delimited files)", "url": "https://www.fhwa.dot.gov/bridge/nbi/ascii.cfm", "access": "free download, no key", "status": "fetcher written (fetch_nbi.py); seed is illustrative"},
        {"name": "USACE National Inventory of Dams", "url": "https://nid.sec.usace.army.mil", "access": "free download (CSV export from the portal)", "status": "fetcher documented (fetch_nid.py); seed is illustrative"},
        {"name": "OpenFEMA disaster declarations v2", "url": "https://www.fema.gov/openfema-data-page/disaster-declarations-summaries-v2", "access": "free API, no key", "status": "fetcher written (fetch_fema_floods.py); seed is illustrative"},
        {"name": "OpenStreetMap (exposure: hospitals, schools, routes)", "url": "https://www.openstreetmap.org", "access": "Overpass API, free", "status": "not yet used"},
        {"name": "Replacement cost column", "url": "", "access": "seed only", "status": "illustrative; NBI item 94-96 (improvement cost) is the real source"},
    ]

    # ---- helpers ------------------------------------------------------------------------------------------------
    @staticmethod
    def _effective_age(row: dict) -> int:
        recon = row.get("year_reconstructed")
        base = int(recon) if recon not in (None, "", "None") and str(recon).strip() else int(row["year_built"])
        return AS_OF.year - base

    def _bridge_row(self, data, sid: str):
        sql = f"SELECT * FROM bridges WHERE structure_id = '{sid}'"
        r = data.run_sql(sql)
        return sql, r

    def _dam_row(self, data, did: str):
        sql = f"SELECT * FROM dams WHERE dam_id = '{did}'"
        r = data.run_sql(sql)
        return sql, r

    # ---- scout ---------------------------------------------------------------------------------------------------
    def scout(self, data, limit):
        out: list[Signal] = []
        sql_b = ("SELECT structure_id, name, county, lat, lon, year_built, year_reconstructed, design_life_years, deck_rating, superstructure_rating, "
                 "substructure_rating, adt, scour_critical, posted_load_limit, replacement_cost_usd FROM bridges "
                 "WHERE LEAST(deck_rating, superstructure_rating, substructure_rating) <= 4 "
                 f"   OR ({AS_OF.year} - COALESCE(CAST(NULLIF(CAST(year_reconstructed AS VARCHAR), '') AS INTEGER), year_built)) >= design_life_years "
                 "ORDER BY adt DESC")
        rb = data.run_sql(sql_b)
        for r in rb["rows"]:
            min_rating = min(int(r["deck_rating"]), int(r["superstructure_rating"]), int(r["substructure_rating"]))
            age = self._effective_age(r)
            deficit = max(1, 5 - min_rating) + (1 if age >= int(r["design_life_years"]) else 0)
            harm = int(r["adt"]) * deficit
            out.append(Signal(
                id=r["structure_id"],
                label=f"Bridge {r['name']}: ratings {r['deck_rating']}/{r['superstructure_rating']}/{r['substructure_rating']}, ADT {int(r['adt']):,}, {age} years old",
                score=float(harm), sql=sql_b, rows=rb["rows_n"],
                props={**{k: (str(v) if k in ("year_reconstructed",) else v) for k, v in r.items()}, "asset": "bridge",
                       "min_rating": min_rating, "effective_age": age, "harm_index": harm, "deficit": deficit}))
        sql_d = ("SELECT dam_id, name, lat, lon, year_completed, hazard_class, condition, last_inspection, population_downstream, eap_present, replacement_cost_usd "
                 "FROM dams WHERE condition IN ('poor','unsatisfactory') OR (hazard_class = 'high' AND CAST(eap_present AS VARCHAR) IN ('false','0','f')) "
                 "ORDER BY population_downstream DESC")
        rd = data.run_sql(sql_d)
        for r in rd["rows"]:
            deficit = CONDITION_DEFICIT.get(str(r["condition"]), 1) + (1 if r["hazard_class"] == "high" else 0) + (1 if not _b(r["eap_present"]) else 0)
            harm = int(r["population_downstream"]) * max(1, deficit)
            age = AS_OF.year - int(r["year_completed"])
            out.append(Signal(
                id=r["dam_id"],
                label=f"Dam {r['name']}: {r['condition']} condition, {r['hazard_class']} hazard, {int(r['population_downstream']):,} people downstream, {age} years old",
                score=float(harm), sql=sql_d, rows=rd["rows_n"],
                props={**dict(r), "asset": "dam", "effective_age": age, "harm_index": harm, "deficit": deficit}))
        out.sort(key=lambda s: -s.score)
        return out[:limit]

    # ---- hypotheses --------------------------------------------------------------------------------------------
    def hypotheses(self, signal, data):
        if signal.props.get("asset") == "dam":
            return [Hypothesis("age", "Past nominal design life (50 years)"),
                    Hypothesis("hazard_without_eap", "High-hazard dam with no emergency action plan"),
                    Hypothesis("deferred_inspection", "Inspection overdue for its hazard class"),
                    Hypothesis("flood_exposure", "Repeated flood events in the county")]
        return [Hypothesis("age_past_design_life", "Past design life (age since build or last reconstruction)"),
                Hypothesis("scour_flood_exposure", "Scour-critical structure in a flood-prone county"),
                Hypothesis("deferred_inspection", "Inspection overdue (> 1.5 x interval)"),
                Hypothesis("overload_traffic_growth", "Traffic grew >= 30% since the ADT count and the bridge is not posted")]

    # ---- tests -------------------------------------------------------------------------------------------------
    def test(self, signal, hyp, data):
        if signal.props.get("asset") == "dam":
            return self._test_dam(signal, hyp, data)
        return self._test_bridge(signal, hyp, data)

    def _test_bridge(self, signal, hyp, data):
        sid = signal.id
        sql, r = self._bridge_row(data, sid)
        row = r["rows"][0]
        if hyp.id == "age_past_design_life":
            age, life = self._effective_age(row), int(row["design_life_years"])
            basis = f"since reconstruction {row['year_reconstructed']}" if str(row.get("year_reconstructed") or "").strip() else f"since build {row['year_built']}"
            ok = age >= life
            return TestResult(hyp.id, "support" if ok else "reject",
                              f"effective age {age} years ({basis}) vs design life {life} years ({'past' if ok else 'within'} design life)", sql, r["rows_n"], {"age": age, "design_life": life})
        if hyp.id == "scour_flood_exposure":
            sql2 = f"SELECT SUM(events) AS events FROM floods WHERE county = '{row['county']}' AND year BETWEEN {AS_OF.year - 4} AND {AS_OF.year}"
            r2 = data.run_sql(sql2)
            ev = int(r2["rows"][0]["events"] or 0)
            scour = _b(row["scour_critical"])
            ok = scour and ev >= 3
            why = f"scour-critical = {str(scour).lower()}, {ev} flood events in {row['county']} County in 5 years"
            why += " (scour exposure supported)" if ok else (" (not scour-critical)" if not scour else " (fewer than 3 floods)")
            return TestResult(hyp.id, "support" if ok else "reject", why, f"{sql};\n{sql2}", r["rows_n"] + r2["rows_n"], {"scour_critical": scour, "floods_5y": ev})
        if hyp.id == "deferred_inspection":
            last = date.fromisoformat(str(row["last_inspection"])[:10])
            months = _months_between(last, AS_OF)
            limit = int(row["inspection_interval_months"]) * 1.5
            ok = months > limit
            return TestResult(hyp.id, "support" if ok else "reject",
                              f"last inspection {last.isoformat()}, {months} months ago; interval {row['inspection_interval_months']} months (overdue past {limit:.0f} months: {'yes' if ok else 'no'})",
                              sql, r["rows_n"], {"months_since_inspection": months, "overdue_months": max(0, months - int(row['inspection_interval_months']))})
        if hyp.id == "overload_traffic_growth":
            sql2 = f"SELECT year, adt_index FROM traffic_growth WHERE county = '{row['county']}' AND year IN ({int(row['adt_year'])}, {AS_OF.year})"
            r2 = data.run_sql(sql2)
            idx = {int(x["year"]): float(x["adt_index"]) for x in r2["rows"]}
            if int(row["adt_year"]) not in idx or AS_OF.year not in idx:
                return TestResult(hyp.id, "uncertain", f"no traffic index for {row['county']} in {row['adt_year']} or {AS_OF.year}", f"{sql};\n{sql2}", r2["rows_n"])
            growth = idx[AS_OF.year] / idx[int(row["adt_year"])] - 1
            posted = _b(row["posted_load_limit"])
            ok = growth >= 0.30 and not posted
            return TestResult(hyp.id, "support" if ok else "reject",
                              f"county traffic index +{growth * 100:.0f}% since the {row['adt_year']} count (ADT {int(row['adt']):,}); posted load limit = {str(posted).lower()}"
                              + (" (overload plausible)" if ok else (" (growth below 30%)" if growth < 0.30 else " (already posted)")),
                              f"{sql};\n{sql2}", r["rows_n"] + r2["rows_n"], {"growth_pct": round(growth * 100, 1), "posted": posted})
        return TestResult(hyp.id, "uncertain", "no test defined", None, 0)

    def _test_dam(self, signal, hyp, data):
        sql, r = self._dam_row(data, signal.id)
        row = r["rows"][0]
        if hyp.id == "age":
            age = AS_OF.year - int(row["year_completed"])
            ok = age >= DAM_DESIGN_LIFE
            return TestResult(hyp.id, "support" if ok else "reject", f"completed {row['year_completed']}, {age} years old vs nominal {DAM_DESIGN_LIFE}-year life", sql, r["rows_n"], {"age": age})
        if hyp.id == "hazard_without_eap":
            eap = _b(row["eap_present"])
            ok = row["hazard_class"] == "high" and not eap
            return TestResult(hyp.id, "support" if ok else "reject",
                              f"hazard class {row['hazard_class']}, emergency action plan present = {str(eap).lower()}, {int(row['population_downstream']):,} people downstream",
                              sql, r["rows_n"], {"hazard": row["hazard_class"], "eap": eap})
        if hyp.id == "deferred_inspection":
            last = date.fromisoformat(str(row["last_inspection"])[:10])
            months = _months_between(last, AS_OF)
            interval = DAM_INTERVAL_MONTHS.get(str(row["hazard_class"]), 24)
            ok = months > interval * 1.5
            return TestResult(hyp.id, "support" if ok else "reject",
                              f"last inspection {last.isoformat()}, {months} months ago; {row['hazard_class']}-hazard interval {interval} months (overdue: {'yes' if ok else 'no'})",
                              sql, r["rows_n"], {"months_since_inspection": months})
        if hyp.id == "flood_exposure":
            # nearest county by seed convention: dams carry no county column in NID exports, so use the closest bridge county by lat/lon
            sql2 = (f"SELECT county FROM bridges ORDER BY (lat - {float(row['lat'])})*(lat - {float(row['lat'])}) + (lon - {float(row['lon'])})*(lon - {float(row['lon'])}) LIMIT 1")
            county = data.run_sql(sql2)["rows"][0]["county"]
            sql3 = f"SELECT SUM(events) AS events FROM floods WHERE county = '{county}' AND year BETWEEN {AS_OF.year - 4} AND {AS_OF.year}"
            r3 = data.run_sql(sql3)
            ev = int(r3["rows"][0]["events"] or 0)
            ok = ev >= 3
            return TestResult(hyp.id, "support" if ok else "reject", f"{ev} flood events in {county} County in 5 years ({'repeated' if ok else 'fewer than 3'})",
                              f"{sql};\n{sql2};\n{sql3}", r["rows_n"] + 1 + r3["rows_n"], {"county": county, "floods_5y": ev})
        return TestResult(hyp.id, "uncertain", "no test defined", None, 0)

    # ---- plan --------------------------------------------------------------------------------------------------
    def plan(self, signal, verdicts, data):
        sup = {v.hypothesis_id: v for v in verdicts if v.verdict == "support"}
        p = signal.props
        harm = p.get("harm_index")
        acts: list[Action] = []
        pr = 1
        if p.get("asset") == "bridge":
            nm = p["name"]
            if "overload_traffic_growth" in sup or (p.get("min_rating", 9) <= 4 and "age_past_design_life" in sup):
                acts.append(Action(f"{signal.id}-post", f"Load-rate and post {nm}", pr, f"min rating {p.get('min_rating')}; {sup.get('overload_traffic_growth', sup.get('age_past_design_life')).reason}", {"harm_index": harm})); pr += 1
            if "scour_flood_exposure" in sup:
                acts.append(Action(f"{signal.id}-scour", f"Scour countermeasures and post-flood inspection at {nm}", pr, sup["scour_flood_exposure"].reason, {"harm_index": harm})); pr += 1
            if "deferred_inspection" in sup:
                od = sup["deferred_inspection"].data.get("overdue_months", 0)
                acts.append(Action(f"{signal.id}-inspect", f"Inspect {nm} now (overdue {od} months)", pr, sup["deferred_inspection"].reason, {"harm_index": harm})); pr += 1
            if "age_past_design_life" in sup:
                acts.append(Action(f"{signal.id}-rehab", f"Programme rehabilitation or replacement of {nm}", pr, sup["age_past_design_life"].reason, {"harm_index": harm, "replacement_cost_usd_illustrative": p.get("replacement_cost_usd")})); pr += 1
        else:
            nm = p["name"]
            if "hazard_without_eap" in sup:
                acts.append(Action(f"{signal.id}-eap", f"Write and exercise an emergency action plan for {nm}", pr, sup["hazard_without_eap"].reason, {"harm_index": harm})); pr += 1
            if "deferred_inspection" in sup:
                acts.append(Action(f"{signal.id}-inspect", f"Inspect {nm} now", pr, sup["deferred_inspection"].reason, {"harm_index": harm})); pr += 1
            if "age" in sup or str(p.get("condition")) in ("poor", "unsatisfactory"):
                acts.append(Action(f"{signal.id}-rehab", f"Commission a condition assessment and rehabilitation design for {nm}", pr, f"condition {p.get('condition')}; " + (sup["age"].reason if "age" in sup else ""), {"harm_index": harm, "replacement_cost_usd_illustrative": p.get("replacement_cost_usd")})); pr += 1
            if "flood_exposure" in sup:
                acts.append(Action(f"{signal.id}-spillway", f"Check spillway capacity at {nm} against recent floods", pr, sup["flood_exposure"].reason, {"harm_index": harm})); pr += 1
        if not acts:
            acts.append(Action(f"{signal.id}-inspect", f"Send an inspector to {p['name']}", 1, "signal present but no cause supported; inspect first", {"harm_index": harm}))
        # region-level debt estimate (illustrative cost column)
        sql = ("SELECT SUM(replacement_cost_usd * (CASE WHEN LEAST(deck_rating, superstructure_rating, substructure_rating) <= 4 THEN 0.6 "
               f"WHEN ({AS_OF.year} - COALESCE(CAST(NULLIF(CAST(year_reconstructed AS VARCHAR), '') AS INTEGER), year_built)) >= design_life_years THEN 0.3 ELSE 0 END)) AS debt_usd FROM bridges")
        debt = data.run_sql(sql)["rows"][0]["debt_usd"] or 0
        acts.append(Action(f"{signal.id}-debt", f"Publish region maintenance debt: ${float(debt) / 1e6:,.0f} M (illustrative)", pr,
                           "Σ replacement cost × condition deficit (0.6 for poor, 0.3 for past design life); cost column is illustrative until NBI items 94-96 are loaded",
                           {"debt_usd_illustrative": float(debt), "sql": sql}))
        return acts

    def extra_json(self, data):
        return {"center": [40.44, -79.99], "zoom": 10, "as_of": AS_OF.isoformat()}


DOMAIN = MaintenanceDebtDomain()
