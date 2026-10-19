"""Kessler — conjunction screening and coordination for Earth orbit.

Scout propagates the catalogue 7 days ahead and flags pairs below 5 km. Investigator names four competing reasons a
pair is converging. Skeptic tests each against the object registry and fragmentation-event table with SQL. Planner
decides who should manoeuvre and drafts the coordination message; nothing is sent until a human approves.
"""
from __future__ import annotations
from datetime import datetime, timezone
from whycore.domain import Action, Domain, Hypothesis, Signal, TestResult
from app.orbit import screen

THRESHOLD_KM = 5.0
WINDOW_DAYS = 7.0
OBJECT_SQL = ("SELECT object_id, name, type, owner, country, manoeuvrable, launch_year, parent_event, mass_kg, a_km, e, "
              "inc_deg, raan_deg, argp_deg, m0_deg, perigee_km, apogee_km FROM objects")


def _q(s: str) -> str:
    return "'" + str(s).replace("'", "''") + "'"


class KesslerDomain(Domain):
    name = "kessler"
    title = "Kessler · conjunction screening and coordination"
    track = "03"
    question = "Which objects come dangerously close in the next 7 days, why, and who should manoeuvre?"
    description = ("Screens every tracked object against every other for the next 7 days (two-body + J2, 5 km threshold), "
                   "explains why each close approach is happening, and drafts who should move. Illustrative orbital "
                   "elements; run app/data/fetch_celestrak.py for live data. Screening, not operations.")
    views = {
        "objects": "SELECT object_id, name, type, owner, country, manoeuvrable, launch_year, parent_event, perigee_km, apogee_km, inc_deg FROM objects ORDER BY type, name",
        "objects_by_type": "SELECT type, COUNT(*) AS n, MIN(perigee_km) AS min_perigee_km, MAX(apogee_km) AS max_apogee_km FROM objects GROUP BY type ORDER BY n DESC",
        "fragmentation_events": "SELECT event_id, parent_object, date, pieces, altitude_km, cause FROM fragmentation_events ORDER BY date DESC",
        "owners": "SELECT owner, country, COUNT(*) AS objects, SUM(CASE WHEN manoeuvrable THEN 1 ELSE 0 END) AS manoeuvrable FROM objects GROUP BY owner, country ORDER BY objects DESC",
    }
    sources = [
        {"name": "CelesTrak GP element sets (all active objects)", "url": "https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=json", "access": "free, no key", "status": "fetcher written (app/data/fetch_celestrak.py); seed is illustrative"},
        {"name": "UN Register of Objects Launched into Outer Space", "url": "https://www.unoosa.org/oosa/en/spaceobjectregister/index.html", "access": "free, web", "status": "stub fetcher; owner/country columns illustrative"},
        {"name": "Space-Track.org (18 SDS catalogue)", "url": "https://www.space-track.org", "access": "free login", "status": "not used"},
        {"name": "ESA DISCOS fragmentation events", "url": "https://discosweb.esoc.esa.int", "access": "API key", "status": "not used; fragmentation_events.csv illustrative"},
    ]

    # ---- Scout --------------------------------------------------------------------------------------------------
    def scout(self, data, limit):
        res = data.run_sql(OBJECT_SQL)
        objs = res["rows"]
        conj = screen(objs, days=WINDOW_DAYS, threshold_km=THRESHOLD_KM)
        by_id = {o["object_id"]: o for o in objs}
        out = []
        for c in conj[:limit]:
            a, b = by_id[c["a"]], by_id[c["b"]]
            props = {**c, "name_a": a["name"], "name_b": b["name"], "type_a": a["type"], "type_b": b["type"],
                     "owner_a": a["owner"], "owner_b": b["owner"], "window_days": WINDOW_DAYS, "threshold_km": THRESHOLD_KM,
                     "propagator": "two-body + J2 secular, 60 s coarse / 1 s refine"}
            out.append(Signal(id=f"{c['a']}x{c['b']}", label=f"{a['name']} × {b['name']}: {c['miss_km']} km at {c['tca']}",
                              score=round(THRESHOLD_KM / max(c["miss_km"], 0.05), 2), props=props, sql=OBJECT_SQL, rows=res["rows_n"]))
        return out

    # ---- Investigator -------------------------------------------------------------------------------------------
    def hypotheses(self, signal, data):
        return [
            Hypothesis("fragmentation", "Debris from a known fragmentation event is crossing this orbit"),
            Hypothesis("uncontrolled_drift", "An uncontrolled rocket body or debris on a decaying orbit is drifting through"),
            Hypothesis("constellation_phasing", "Two satellites of one operator are phasing past each other in the same shell"),
            Hypothesis("natural_crossing", "Two unrelated controlled payloads on very different planes simply cross"),
        ]

    # ---- Skeptic ------------------------------------------------------------------------------------------------
    def test(self, signal, hyp, data):
        p = signal.props
        a_id, b_id = p["a"], p["b"]
        pair_sql = f"{OBJECT_SQL} WHERE object_id IN ({_q(a_id)}, {_q(b_id)}) ORDER BY object_id"
        pr = data.run_sql(pair_sql)
        A, B = pr["rows"][0], pr["rows"][1]
        tca = datetime.strptime(p["tca"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)

        if hyp.id == "fragmentation":
            parents = [o["parent_event"] for o in (A, B) if o["parent_event"]]
            if not parents:
                return TestResult(hyp.id, "reject", "neither object is catalogued as a fragment of a known event", pair_sql, pr["rows_n"], {"parents": []})
            sql = f"SELECT event_id, date, pieces, altitude_km FROM fragmentation_events WHERE event_id IN ({', '.join(_q(x) for x in parents)})"
            er = data.run_sql(sql)
            for ev in er["rows"]:
                years = (tca - datetime.strptime(str(ev["date"])[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)).days / 365.25
                dalt = abs(float(ev["altitude_km"]) - float(p["alt_km"]))
                if years <= 3.0 and dalt <= 150:
                    return TestResult(hyp.id, "support", f"{ev['event_id']} ({ev['pieces']} pieces, {years:.1f} years ago, {ev['altitude_km']} km) matches the {p['alt_km']} km conjunction altitude within {dalt:.0f} km", sql, er["rows_n"], dict(ev))
                return TestResult(hyp.id, "uncertain", f"{ev['event_id']} is {years:.1f} years old and {dalt:.0f} km from the conjunction altitude: a fragment, but an aged one", sql, er["rows_n"], dict(ev))
            return TestResult(hyp.id, "uncertain", "parent event not in the fragmentation table", sql, er["rows_n"])

        if hyp.id == "uncontrolled_drift":
            drifters = [o for o in (A, B) if o["type"] in ("rocket_body", "debris") and not _truthy(o["manoeuvrable"]) and float(o["perigee_km"]) < 400]
            if drifters:
                d = drifters[0]
                return TestResult(hyp.id, "support", f"{d['name']} is an uncontrolled {d['type'].replace('_', ' ')} with perigee {d['perigee_km']} km (below 400 km, decaying through the {p['alt_km']} km band)", pair_sql, pr["rows_n"], {"object": d["object_id"], "perigee_km": d["perigee_km"]})
            low = min(float(A["perigee_km"]), float(B["perigee_km"]))
            return TestResult(hyp.id, "reject", f"no uncontrolled object with a decaying perigee in the pair (lowest perigee {low:.0f} km; types {A['type']}, {B['type']})", pair_sql, pr["rows_n"], {"min_perigee_km": low})

        if hyp.id == "constellation_phasing":
            same_owner = A["owner"] == B["owner"] and A["type"] == "payload" and B["type"] == "payload"
            da, di = abs(float(A["a_km"]) - float(B["a_km"])), abs(float(A["inc_deg"]) - float(B["inc_deg"]))
            if same_owner and da < 5 and di < 1:
                return TestResult(hyp.id, "support", f"both are {A['owner']} payloads in one shell (Δa {da:.1f} km, Δi {di:.2f}°): a phasing pass, operator can resolve internally", pair_sql, pr["rows_n"], {"da_km": da, "di_deg": di})
            return TestResult(hyp.id, "reject", f"not one operator’s shell: owners {A['owner']} / {B['owner']}, Δa {da:.0f} km, Δi {di:.1f}°", pair_sql, pr["rows_n"], {"da_km": da, "di_deg": di})

        if hyp.id == "natural_crossing":
            di = abs(float(A["inc_deg"]) - float(B["inc_deg"]))
            if di > 20 and A["type"] != "debris" and B["type"] != "debris" and not any(o["parent_event"] for o in (A, B)):
                return TestResult(hyp.id, "support", f"planes differ by {di:.1f}° and both are catalogued payloads with no fragment parent: an ordinary crossing at {p['rel_speed_km_s']} km/s", pair_sql, pr["rows_n"], {"di_deg": di})
            return TestResult(hyp.id, "reject", f"Δi {di:.1f}° (needs > 20°) or a debris / fragment object in the pair", pair_sql, pr["rows_n"], {"di_deg": di})
        return TestResult(hyp.id, "uncertain", "no test for this hypothesis")

    # ---- Planner ------------------------------------------------------------------------------------------------
    def plan(self, signal, verdicts, data):
        p = signal.props
        sup = [v.hypothesis_id for v in verdicts if v.verdict == "support"]
        cause = sup[0] if sup else "unexplained"
        pr = data.run_sql(f"{OBJECT_SQL} WHERE object_id IN ({_q(p['a'])}, {_q(p['b'])}) ORDER BY object_id")
        A, B = pr["rows"][0], pr["rows"][1]
        movers = [o for o in (A, B) if _truthy(o["manoeuvrable"]) and o["type"] == "payload"]
        movers.sort(key=lambda o: float(o["mass_kg"]))   # lighter spacecraft = cheaper manoeuvre proxy
        acts = []
        if movers:
            m = movers[0]
            other = B if m is A else A
            msg = (f"CONJUNCTION NOTICE (screening) — {m['name']} ({m['owner']}) vs {other['name']} ({other['owner'] or 'uncatalogued owner'}).\n"
                   f"TCA {p['tca']} UTC, miss distance {p['miss_km']} km, relative speed {p['rel_speed_km_s']} km/s, altitude {p['alt_km']} km.\n"
                   f"Assessed cause: {cause.replace('_', ' ')}. Request: {m['owner']} evaluates an avoidance manoeuvre for {m['name']}; "
                   f"{'please confirm your own screening and whether you intend to move' if _truthy(other['manoeuvrable']) else 'the other object cannot manoeuvre'}.\n"
                   f"Source: two-body + J2 screening; re-screen with operator ephemerides before acting.")
            acts.append(Action(f"{signal.id}-move", f"Ask {m['owner']} to plan an avoidance manoeuvre for {m['name']}", 1,
                               f"miss {p['miss_km']} km < {THRESHOLD_KM} km; {m['name']} is the manoeuvrable, lighter spacecraft; cause: {cause.replace('_', ' ')}",
                               {"draft_message": msg, "to": m["owner"], "object": m["object_id"]}))
            if cause == "constellation_phasing":
                acts[0].label = f"Notify {m['owner']} to resolve internal phasing between {A['name']} and {B['name']}"
        else:
            acts.append(Action(f"{signal.id}-watch", f"Watch only: neither {A['name']} nor {B['name']} can manoeuvre", 1,
                               f"miss {p['miss_km']} km; no actor; publish to the shared watch list", {"draft_message": "No manoeuvrable party; conjunction added to the public watch list."}))
        acts.append(Action(f"{signal.id}-rescreen", f"Re-screen {A['name']} × {B['name']} at TCA − 24 h with fresh elements", 2,
                           "two-body + J2 screening drifts; refresh elements before any decision", {"tca": p["tca"]}))
        if cause == "fragmentation":
            acts.append(Action(f"{signal.id}-cloud", "Flag the parent fragmentation cloud for a full-catalogue re-screen", 3,
                               "one fragment close means siblings may follow", {}))
        return acts

    def explain_prompt(self, signal, verdicts, actions):
        sys_ = ("You brief a satellite operator. Explain in plain language, under 120 words, why this close approach is happening "
                "and what is being proposed. Use only the facts given; every number must appear in the input.")
        p = signal.props
        lines = [f"Conjunction: {p['name_a']} ({p['type_a']}, {p['owner_a']}) and {p['name_b']} ({p['type_b']}, {p['owner_b'] or 'unknown owner'})",
                 f"TCA {p['tca']}, miss {p['miss_km']} km, relative speed {p['rel_speed_km_s']} km/s, altitude {p['alt_km']} km"]
        for v in verdicts:
            lines.append(f"- {v.hypothesis_id}: {v.verdict.upper()} — {v.reason}")
        lines.append("Proposed (drafts): " + "; ".join(f"{a.priority}. {a.label}" for a in actions))
        return sys_, "\n".join(lines)

    def extra_json(self, data):
        return {"center": [0, 0], "zoom": 2, "threshold_km": THRESHOLD_KM, "window_days": WINDOW_DAYS}


def _truthy(v) -> bool:
    return str(v).strip().lower() in ("true", "1", "t", "yes")


DOMAIN = KesslerDomain()
