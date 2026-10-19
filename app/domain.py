"""Advocate — an explain-why agent whose only client is a body of water with legal personhood.

Pilot client: the Mar Menor lagoon (Spain, Ley 19/2022). Nothing here is Mar Menor specific: the client, its stations,
thresholds, permits and pending decisions are rows; add a client (Whanganui, Atrato, …) by loading its rows.

Signals   (a) open decisions near the client with a deadline inside 90 days of the data's as-of date
          (b) water-quality parameters at the client's own stations breaching or trending toward a legal threshold
Causes    trend  : agricultural_runoff · urban_discharge · groundwater_abstraction · natural_variation
          decision: increases_nutrient_load · increases_abstraction · no_material_effect
Skeptic   numbers only, SQL attached: lead/lag of inflow vs lagoon, permit volumes within 10 km, slope vs seasonal
          amplitude, keyword + distance rules for decisions
Actions   drafts for the human guardians: an objection or notice (structured, with legal basis and numbers), a monitoring
          request, a watch item. The agent never files anything.
"""
from __future__ import annotations
import numpy as np
from whycore.domain import Action, Domain, Hypothesis, Signal, TestResult

NEAR_KM = 15.0          # decisions closer than this are the client's business
PERMIT_KM = 10.0        # permits that can plausibly load the client
TREND_PCT = 15.0        # 12-month change that counts as a trend
LAG_CORR = 0.35         # minimum cross-correlation for "inflow leads lagoon"
NUTRIENT_WORDS = ("fertilis", "fertiliz", "nitrogen", "nitrate", "manure", "discharge", "wastewater", "sewage", "outfall", "edar")
ABSTRACTION_WORDS = ("abstraction", "irrigation", "groundwater", "well", "desalination", "pumping", "borehole")


def _series(data, station: str, parameter: str) -> tuple[list, np.ndarray, str, int]:
    sql = (f"SELECT date, value FROM measurements WHERE station_id = '{station}' AND parameter = '{parameter}' ORDER BY date")
    r = data.run_sql(sql)
    return [row["date"] for row in r["rows"]], np.array([float(row["value"]) for row in r["rows"]]), sql, r["rows_n"]


def _pct_change_12m(v: np.ndarray) -> float:
    if len(v) < 24:
        return 0.0
    a, b = v[-24:-12].mean(), v[-12:].mean()
    return float((b - a) / abs(a) * 100) if a else 0.0


def _lead_lag(x: np.ndarray, y: np.ndarray, max_lag: int = 3) -> tuple[int, float]:
    """Best lag k ≥ 0 at which x[t-k] explains y[t] (month-over-month changes, last 36 months)."""
    dx, dy = np.diff(x[-37:]), np.diff(y[-37:])
    best = (0, -1.0)
    for k in range(0, max_lag + 1):
        a, b = dx[: len(dx) - k] if k else dx, dy[k:]
        if len(a) < 8 or a.std() == 0 or b.std() == 0:
            continue
        c = float(np.corrcoef(a, b)[0, 1])
        if c > best[1]:
            best = (k, c)
    return best


class AdvocateDomain(Domain):
    name = "advocate"
    title = "Advocate · an agent for a river with rights"
    track = "03"
    question = "Which pending decisions and trends threaten the Mar Menor, why, and what objection should its guardians file?"
    description = ("The client is a body of water with legal personhood. The agent reads every open dataset about it, finds pending "
                   "decisions and worsening trends, tests competing causes with numbers, and drafts the objection its human guardians "
                   "may file. Seed data is illustrative (see app/data/seed/README.md); fetchers pull the real series.")
    views = {
        "open_decisions": "SELECT decision_id, title, authority, kind, distance_km, deadline, status FROM decisions WHERE status = 'open' ORDER BY deadline",
        "lagoon_trends": ("SELECT m.station_id, s.name, m.parameter, m.date, m.value FROM measurements m JOIN stations s ON s.station_id = m.station_id "
                          "WHERE s.kind = 'lagoon' AND m.date >= (SELECT MAX(date) FROM measurements) - INTERVAL '12 months' ORDER BY m.parameter, m.station_id, m.date"),
        "permits_near": f"SELECT permit_id, holder, kind, volume, unit, distance_km, status, expiry FROM permits WHERE distance_km <= {PERMIT_KM} ORDER BY distance_km",
        "thresholds": "SELECT parameter, limit_value, direction, legal_basis FROM thresholds",
    }
    sources = [
        {"name": "Ley 19/2022 — legal personality of the Mar Menor (BOE)", "url": "https://www.boe.es/eli/es/l/2022/09/30/19", "access": "open text", "status": "statute; quoted as legal basis"},
        {"name": "Ley 3/2020 Mar Menor (Región de Murcia) — nutrient limits", "url": "https://www.borm.es", "access": "open text", "status": "legal basis for thresholds"},
        {"name": "CHS (Confederación Hidrográfica del Segura) open data — permits, gauges", "url": "https://www.chsegura.es", "access": "open portal; API shape unconfirmed", "status": "fetch_chs_opendata.py is a documented stub"},
        {"name": "EEA Waterbase / WISE water quality", "url": "https://www.eea.europa.eu/data-and-maps/data/waterbase-water-quality-icm", "access": "bulk CSV, free", "status": "fetch_eea_waterbase.py (run with internet)"},
        {"name": "Municipal planning registers (Cartagena, Los Alcázares, San Javier)", "url": "", "access": "open notices, manual", "status": "seed decisions are illustrative"},
        {"name": "Other legal-person clients: Whanganui (NZ, 2017), Atrato (CO, 2016)", "url": "", "access": "statutes", "status": "add as rows in clients"},
    ]

    # ---- helpers --------------------------------------------------------------------------------------------------
    def _client(self, data) -> dict:
        return data.run_sql("SELECT client_id, name, statute, lat, lon, guardian_body FROM clients ORDER BY client_id")["rows"][0]

    def _as_of(self, data) -> str:
        return str(data.run_sql("SELECT MAX(date) AS d FROM measurements")["rows"][0]["d"])[:10]

    # ---- Scout ----------------------------------------------------------------------------------------------------
    def scout(self, data, limit):
        client = self._client(data)
        signals: list[Signal] = []
        sql_d = (f"SELECT decision_id, title, authority, kind, distance_km, deadline, summary FROM decisions WHERE status = 'open' "
                 f"AND distance_km <= {NEAR_KM} AND deadline <= (SELECT MAX(date) FROM measurements) + INTERVAL '90 days' ORDER BY distance_km")
        rd = data.run_sql(sql_d)
        for r in rd["rows"]:
            score = (NEAR_KM - float(r["distance_km"])) / NEAR_KM * 10 + (3 if r["kind"] != "planning" else 0)
            signals.append(Signal(id=f"dec-{r['decision_id']}", label=f"Decision: {r['title']} (deadline {str(r['deadline'])[:10]})",
                                  score=round(score, 2), sql=sql_d, rows=rd["rows_n"],
                                  props={**{k: (str(v) if k in ('deadline',) else v) for k, v in r.items()}, "kind_of_signal": "decision",
                                         "lat": client["lat"], "lon": client["lon"], "client": client["name"]}))
        sql_s = "SELECT station_id, name, lat, lon FROM stations WHERE kind = 'lagoon' ORDER BY station_id"
        sql_t = "SELECT parameter, limit_value, direction FROM thresholds WHERE direction <> 'none'"
        thresholds = data.run_sql(sql_t)["rows"]
        for st in data.run_sql(sql_s)["rows"]:
            for th in thresholds:
                dates, v, sql_m, n = _series(data, st["station_id"], th["parameter"])
                if n < 24:
                    continue
                pct = _pct_change_12m(v)
                bad = pct >= TREND_PCT if th["direction"] == "above" else pct <= -TREND_PCT
                breach = (v[-12:].mean() > float(th["limit_value"])) if th["direction"] == "above" else (v[-12:].mean() < float(th["limit_value"]))
                if bad or breach:
                    signals.append(Signal(id=f"trend-{st['station_id']}-{th['parameter']}",
                                          label=f"Trend: {th['parameter'].replace('_', ' ')} at {st['name']} {pct:+.0f}% in 12 months" + (" (above legal limit)" if breach else ""),
                                          score=round(abs(pct) / 10 + (5 if breach else 0), 2), sql=sql_m, rows=n,
                                          props={"kind_of_signal": "trend", "station_id": st["station_id"], "station": st["name"], "parameter": th["parameter"],
                                                 "pct_12m": round(pct, 1), "limit": th["limit_value"], "direction": th["direction"], "mean_12m": round(float(v[-12:].mean()), 3),
                                                 "lat": st["lat"], "lon": st["lon"], "client": client["name"]}))
        return signals[:limit]

    # ---- Investigator ---------------------------------------------------------------------------------------------
    def hypotheses(self, signal, data):
        if signal.props["kind_of_signal"] == "trend":
            return [Hypothesis("agricultural_runoff", "Agricultural runoff through the inflow channels"),
                    Hypothesis("urban_discharge", "Urban wastewater discharge"),
                    Hypothesis("groundwater_abstraction", "Groundwater abstraction pulling nitrate-rich water in"),
                    Hypothesis("natural_variation", "Natural seasonal variation")]
        return [Hypothesis("increases_nutrient_load", "The decision increases nutrient load on the client"),
                Hypothesis("increases_abstraction", "The decision increases water abstraction from the client's basin"),
                Hypothesis("no_material_effect", "No material effect on the client")]

    # ---- Skeptic --------------------------------------------------------------------------------------------------
    def test(self, signal, hyp, data):
        p = signal.props
        if p["kind_of_signal"] == "decision":
            text = (str(p.get("title", "")) + " " + str(p.get("summary", ""))).lower()
            sql = f"SELECT kind, distance_km, summary FROM decisions WHERE decision_id = '{p['decision_id']}'"
            r = data.run_sql(sql)
            d = float(p["distance_km"])
            nutrient = any(w in text for w in NUTRIENT_WORDS) and p["kind"] in ("permit_renewal", "infrastructure")
            abstraction = any(w in text for w in ABSTRACTION_WORDS)
            if hyp.id == "increases_nutrient_load":
                ok = nutrient and d <= 5
                why = (f"{p['kind']} mentioning nutrient terms, {d:.0f} km from the shore" if ok else
                       f"no nutrient-related terms in a {p['kind']} decision" if not nutrient else f"{d:.0f} km away, beyond the 5 km loading zone")
                return TestResult(hyp.id, "support" if ok else "reject", why, sql, r["rows_n"], {"distance_km": d, "nutrient_terms": nutrient})
            if hyp.id == "increases_abstraction":
                ok = abstraction and d <= PERMIT_KM
                return TestResult(hyp.id, "support" if ok else "reject",
                                  (f"abstraction terms present, {d:.0f} km away" if ok else "no abstraction, irrigation or groundwater terms in the decision"),
                                  sql, r["rows_n"], {"abstraction_terms": abstraction})
            ok = not (nutrient and d <= 5) and not (abstraction and d <= PERMIT_KM)
            return TestResult(hyp.id, "support" if ok else "reject",
                              (f"{p['kind']} decision {d:.0f} km away with no nutrient or abstraction content" if ok else
                               f"cannot be immaterial: nutrient/abstraction content {d:.0f} km from the client"),
                              sql, r["rows_n"], {"distance_km": d})

        # trend signal
        st, par = p["station_id"], p["parameter"]
        dates, lag_v, sql_l, n_l = _series(data, st, par)
        if hyp.id == "agricultural_runoff":
            sql_in = "SELECT station_id FROM stations WHERE kind = 'inflow' ORDER BY station_id"
            inflows = [r["station_id"] for r in data.run_sql(sql_in)["rows"]]
            best = (None, 0, -1.0)
            for s in inflows:
                _, iv, _, n_i = _series(data, s, par)
                if n_i >= 36:
                    k, c = _lead_lag(iv[-len(lag_v):] if len(iv) >= len(lag_v) else iv, lag_v[-len(iv):] if len(iv) < len(lag_v) else lag_v)
                    if c > best[2]:
                        best = (s, k, c)
            sql_p = (f"SELECT COALESCE(SUM(CASE WHEN kind = 'fertiliser_plan' THEN volume ELSE 0 END), 0) AS fert_t, COUNT(*) AS n FROM permits "
                     f"WHERE kind IN ('fertiliser_plan', 'abstraction') AND status IN ('active', 'renewal_pending') AND distance_km <= {PERMIT_KM}")
            rp = data.run_sql(sql_p)["rows"][0]
            fert = float(rp["fert_t"] or 0)
            leads = best[1] >= 1 and best[2] >= LAG_CORR
            ok = leads and fert >= 500
            why = (f"inflow {best[0]} leads the lagoon by {best[1]} month(s), correlation {best[2]:.2f}; {fert:.0f} t/yr nitrogen under active fertiliser plans within {PERMIT_KM:.0f} km"
                   if ok else (f"inflow does not lead the lagoon (best lag {best[1]}, correlation {best[2]:.2f})" if not leads else f"only {fert:.0f} t/yr fertiliser permitted nearby"))
            return TestResult(hyp.id, "support" if ok else "reject", why, f"{sql_l}; {sql_p}", n_l + 1,
                              {"inflow": best[0], "lag_months": best[1], "xcorr": round(best[2], 3), "fertiliser_t_year": fert})
        if hyp.id == "urban_discharge":
            sql_d = f"SELECT permit_id, holder, volume, distance_km FROM permits WHERE kind = 'discharge' AND status = 'active' AND distance_km <= {PERMIT_KM} ORDER BY distance_km"
            rd = data.run_sql(sql_d)
            _, chl, sql_c, n_c = _series(data, st, "chlorophyll_ug_l")
            chl_pct = _pct_change_12m(chl) if n_c >= 24 else 0.0
            ok = rd["rows_n"] > 0 and chl_pct >= TREND_PCT
            if rd["rows_n"] == 0:
                why = f"no active discharge permit within {PERMIT_KM:.0f} km"
            elif ok:
                why = f"{rd['rows'][0]['holder']} discharges {rd['rows'][0]['distance_km']} km away and chlorophyll rose {chl_pct:+.0f}% over the same 12 months"
            else:
                why = f"{rd['rows'][0]['holder']} discharges {rd['rows'][0]['distance_km']} km away, but chlorophyll changed {chl_pct:+.0f}% in the same 12 months: no bloom response, so discharge does not explain this rise"
            return TestResult(hyp.id, "support" if ok else "reject", why, f"{sql_d}; {sql_c}", rd["rows_n"] + n_c, {"chlorophyll_pct_12m": round(chl_pct, 1)})
        if hyp.id == "groundwater_abstraction":
            sql_g = "SELECT station_id FROM stations WHERE kind = 'groundwater' ORDER BY station_id"
            gws = [r["station_id"] for r in data.run_sql(sql_g)["rows"]]
            gw_pct = None
            for g in gws:
                _, gv, _, n_g = _series(data, g, par)
                if n_g >= 24:
                    gw_pct = _pct_change_12m(gv)
            sql_a = f"SELECT COALESCE(SUM(volume), 0) AS m3 FROM permits WHERE kind = 'abstraction' AND status IN ('active', 'renewal_pending') AND distance_km <= {PERMIT_KM}"
            m3 = float(data.run_sql(sql_a)["rows"][0]["m3"] or 0)
            if gw_pct is None:
                return TestResult(hyp.id, "uncertain", "no groundwater station for this parameter", f"{sql_g}; {sql_a}", 1, {})
            ok = gw_pct >= TREND_PCT and m3 >= 500000
            why = (f"groundwater {par.replace('_', ' ')} {gw_pct:+.0f}% in 12 months with {m3:,.0f} m³/yr abstraction nearby" if ok else
                   f"groundwater {par.replace('_', ' ')} changed only {gw_pct:+.0f}% in 12 months ({m3:,.0f} m³/yr abstraction nearby)")
            return TestResult(hyp.id, "support" if ok else "reject", why, f"{sql_g}; {sql_a}", 2, {"gw_pct_12m": round(gw_pct, 1), "abstraction_m3": m3})
        # natural_variation
        base = lag_v[:36] if len(lag_v) >= 60 else lag_v[: len(lag_v) // 2]
        x = np.arange(len(base))
        detr = base - np.polyval(np.polyfit(x, base, 1), x)
        amplitude = float((detr.max() - detr.min()) / 2)
        slope = float(np.polyfit(np.arange(12), lag_v[-12:], 1)[0] * 12)
        ok = abs(slope) <= 2 * amplitude
        why = (f"12-month change {slope:+.2f} is within 2× the 2019–2021 seasonal amplitude ({amplitude:.2f})" if ok else
               f"12-month change {slope:+.2f} is {abs(slope) / amplitude if amplitude else 99:.1f}× the 2019–2021 seasonal amplitude ({amplitude:.2f}); seasonality cannot explain it")
        return TestResult(hyp.id, "support" if ok else "reject", why, sql_l, n_l, {"slope_12m": round(slope, 3), "seasonal_amplitude": round(amplitude, 3)})

    # ---- Planner --------------------------------------------------------------------------------------------------
    def plan(self, signal, verdicts, data):
        client = self._client(data)
        p = signal.props
        sup = [v for v in verdicts if v.verdict == "support"]
        sup_ids = {v.hypothesis_id for v in sup}
        legal = {r["parameter"]: r["legal_basis"] for r in data.run_sql("SELECT parameter, legal_basis FROM thresholds")["rows"]}
        facts = [v.reason for v in verdicts if v.verdict in ("support", "reject")]
        acts: list[Action] = []
        if p["kind_of_signal"] == "decision":
            if sup_ids - {"no_material_effect"}:
                harm = ", ".join(sorted(sup_ids - {"no_material_effect"})).replace("_", " ")
                acts.append(Action(f"{signal.id}-objection", f"Draft objection to: {p['title']}", 1,
                                   f"{harm} supported; deadline {p['deadline']}; guardians decide whether to file",
                                   {"objection": {"addressee": p["authority"], "on_behalf_of": client["name"], "filed_by": client["guardian_body"],
                                                  "legal_basis": [client["statute"], legal.get("nitrate_mg_l", "")],
                                                  "facts": facts, "request": f"Suspend or condition the decision '{p['title']}' pending an impact assessment on {client['name']}",
                                                  "deadline": p["deadline"], "status": "draft — not filed"}}))
                acts.append(Action(f"{signal.id}-monitor", f"Request the authority's impact data for {p['decision_id']}", 2, "needed to turn the draft into a filing"))
            else:
                acts.append(Action(f"{signal.id}-none", f"No objection: evidence insufficient for {p['decision_id']}", 1,
                                   "no harm hypothesis supported; " + "; ".join(facts)[:160]))
            acts.append(Action(f"{signal.id}-watch", f"Watch {p['decision_id']} until {p['deadline']}", 3, "re-run when the file changes"))
            return acts
        # trend
        if sup_ids:
            cause = sup[0].hypothesis_id.replace("_", " ")
            acts.append(Action(f"{signal.id}-notice", f"Draft notice to CHS and CARM: {p['parameter'].replace('_', ' ')} rise at {p['station']} attributed to {cause}", 1,
                               f"{cause} supported with data; {len(verdicts) - len(sup)} alternative causes rejected",
                               {"objection": {"addressee": "Confederación Hidrográfica del Segura; CARM", "on_behalf_of": client["name"], "filed_by": client["guardian_body"],
                                              "legal_basis": [client["statute"], legal.get(p["parameter"], "")], "facts": facts,
                                              "request": f"Enforce the {p['parameter'].replace('_', ' ')} limit ({p['limit']}) and review the permits identified", "status": "draft — not filed"}}))
            acts.append(Action(f"{signal.id}-monitor", f"Request weekly {p['parameter'].replace('_', ' ')} sampling at the inflow and {p['station']}", 2, "confirms the lead-lag before filing"))
        else:
            acts.append(Action(f"{signal.id}-none", f"No objection: cause of the {p['parameter'].replace('_', ' ')} trend not established", 1, "; ".join(facts)[:160]))
        acts.append(Action(f"{signal.id}-watch", f"Watch {p['parameter'].replace('_', ' ')} at {p['station']}", 3, "re-run monthly"))
        return acts

    def explain_prompt(self, signal, verdicts, actions):
        sys_ = ("You write for the human guardians of a body of water that has legal personality. In at most 120 words, plain language, "
                "say what the signal is, which cause the numbers support, which were rejected and why, and what the draft action is. "
                "Use only numbers present in the input. Never say anything has been filed; everything is a draft.")
        lines = [f"Client: {signal.props.get('client')}", f"Signal: {signal.label}"]
        lines += [f"- {v.hypothesis_id}: {v.verdict.upper()} — {v.reason}" for v in verdicts]
        lines.append("Draft actions: " + "; ".join(f"{a.priority}. {a.label}" for a in actions))
        return sys_, "\n".join(lines)

    def extra_json(self, data):
        return {"center": [37.70, -0.78], "zoom": 10}


DOMAIN = AdvocateDomain()
