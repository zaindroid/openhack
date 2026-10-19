"""Last Speakers — documentation triage for endangered languages.

Question: which languages are closest to losing their last fluent speakers, what is blocking their documentation,
and where should a documentation team go first?

Signals  : languages with ≤ 500 speakers or severely/critically endangered, scored by urgency
           urgency = (1 / speakers) × (median speaker age / 70) × (1 − min(1, OPEN archived audio+video hours / 50))
           Closed or unarchived recordings do not count: nobody can learn from them.
Causes   : what blocks documentation — no_recordings · unreachable_speakers · no_orthography · resources_unarchived ·
           no_active_project. Each test is one SQL query over the registers; the verdict comes from the numbers.
Actions  : drafts for a funder or language programme; communities decide. This ranks where to ask, not what to take.
Seed data is ILLUSTRATIVE (invented names and figures in the Glottolog/UNESCO/ELAR column shapes). Run
app/data/fetch_glottolog.py and fill resources/access/projects from the archives for a real run.
"""
from __future__ import annotations
from whycore.domain import Action, Domain, Hypothesis, Signal, TestResult

TARGET_HOURS = 50          # open, archived audio+video hours regarded as a minimal documentation corpus
HOURS_PER_SPEAKER_YEAR = 2  # heuristic: recordable hours per cooperating fluent speaker per field year

OPEN_HOURS_SQL = """
SELECT l.glottocode, l.name, l.family, l.country, l.region, l.lat, l.lon, l.speakers, l.speakers_year,
       l.median_speaker_age, l.endangerment, l.intergenerational_transmission,
       COALESCE(o.open_hours, 0) AS open_hours
FROM languages l
LEFT JOIN (SELECT glottocode, SUM(amount) AS open_hours FROM resources
           WHERE kind IN ('audio_hours', 'video_hours') AND open_access AND archive IS NOT NULL AND archive <> ''
           GROUP BY glottocode) o ON o.glottocode = l.glottocode
"""


def urgency(speakers: float, age: float, open_hours: float) -> float:
    return (1.0 / max(float(speakers), 1.0)) * (float(age) / 70.0) * (1.0 - min(1.0, float(open_hours) / TARGET_HOURS)) * 1000.0


class LastSpeakersDomain(Domain):
    name = "last-speakers"
    title = "Last Speakers · documentation triage"
    track = "03"
    question = ("Which endangered languages are closest to losing their last fluent speakers, what is blocking "
                "documentation, and where should a team go first?")
    description = ("Illustrative seed data in Glottolog / UNESCO / ELAR column shapes (invented names and figures). "
                   "Urgency = 1/speakers × age factor × documentation deficit, counting only OPEN archived recordings. "
                   "Run app/data/fetch_glottolog.py for a real language list.")
    views = {
        "most_urgent": OPEN_HOURS_SQL + """
WHERE l.speakers <= 500 OR l.endangerment IN ('severely', 'critically')
ORDER BY (1.0 / GREATEST(l.speakers, 1)) * (l.median_speaker_age / 70.0) * (1 - LEAST(1.0, COALESCE(o.open_hours, 0) / 50.0)) DESC""",
        "resources_by_language": """
SELECT r.glottocode, l.name, r.kind, r.amount, r.year, r.archive, r.open_access
FROM resources r JOIN languages l ON l.glottocode = r.glottocode
ORDER BY r.glottocode, r.kind""",
        "access_blockers": """
SELECT a.glottocode, l.name, l.country, a.nearest_town_km, a.travel_days, a.permit_required, a.community_contact,
       a.orthography_exists, a.active_linguist,
       (SELECT COUNT(*) FROM projects p WHERE p.glottocode = a.glottocode AND p.status IN ('active', 'planned')) AS live_projects
FROM access a JOIN languages l ON l.glottocode = a.glottocode
ORDER BY a.travel_days DESC, a.permit_required DESC""",
    }
    sources = [
        {"name": "Glottolog (languoids, AES endangerment, coordinates)", "url": "https://glottolog.org", "access": "CC-BY CSV/CLDF download, no key", "status": "fetcher: app/data/fetch_glottolog.py"},
        {"name": "UNESCO World Atlas of Languages", "url": "https://en.wal.unesco.org", "access": "web atlas; export per language", "status": "manual export"},
        {"name": "ELAR — Endangered Languages Archive", "url": "https://www.elararchive.org", "access": "catalogue public; many deposits restricted", "status": "stub: app/data/fetch_elar.py"},
        {"name": "PARADISEC", "url": "https://www.paradisec.org.au", "access": "OAI-PMH catalogue, open", "status": "stub: app/data/fetch_elar.py"},
        {"name": "Ethnologue (speaker counts)", "url": "https://www.ethnologue.com", "access": "paid licence", "status": "not used"},
        {"name": "seed CSVs in app/data/seed", "url": "", "access": "bundled", "status": "illustrative"},
    ]

    # ---- Scout ---------------------------------------------------------------------------------------------------
    def scout(self, data, limit):
        sql = OPEN_HOURS_SQL + "WHERE l.speakers <= 500 OR l.endangerment IN ('severely', 'critically')"
        res = data.run_sql(sql)
        signals = []
        for r in res["rows"]:
            score = urgency(r["speakers"], r["median_speaker_age"], r["open_hours"])
            props = dict(r)
            props["memory_key"] = r["country"]
            props["urgency_formula"] = "1/speakers × age/70 × (1 − min(1, open_hours/50)) × 1000"
            label = (f"{r['name']}: ~{int(r['speakers'])} speakers, median age {int(r['median_speaker_age'])}, "
                     f"{float(r['open_hours']):g} h open recordings")
            signals.append(Signal(id=r["glottocode"], label=label, score=round(score, 3), props=props, sql=sql, rows=res["rows_n"]))
        signals.sort(key=lambda s: -s.score)
        return signals[:limit]

    # ---- Investigator --------------------------------------------------------------------------------------------
    def hypotheses(self, signal, data):
        return [
            Hypothesis("no_recordings", "Too few recordings exist (audio + video under 5 h)"),
            Hypothesis("unreachable_speakers", "Speakers are hard to reach (multi-day travel or permit without a community contact)"),
            Hypothesis("no_orthography", "No practical orthography and almost no lexicon"),
            Hypothesis("resources_unarchived", "Recordings exist but sit closed or outside any archive"),
            Hypothesis("no_active_project", "No active or planned documentation project"),
        ]

    # ---- Skeptic -------------------------------------------------------------------------------------------------
    def test(self, signal, hyp, data):
        g = signal.id
        if hyp.id == "no_recordings":
            sql = (f"SELECT COALESCE(SUM(CASE WHEN kind IN ('audio_hours','video_hours') THEN amount ELSE 0 END), 0) AS hours "
                   f"FROM resources WHERE glottocode = '{g}'")
            r = data.run_sql(sql); hours = float(r["rows"][0]["hours"])
            ok = hours < 5
            return TestResult(hyp.id, "support" if ok else "reject",
                              f"{hours:g} h of audio+video recorded in total ({'under' if ok else 'at or above'} the 5 h floor)",
                              sql, r["rows_n"], {"hours": hours})
        if hyp.id == "unreachable_speakers":
            sql = f"SELECT travel_days, permit_required, community_contact, nearest_town_km FROM access WHERE glottocode = '{g}'"
            r = data.run_sql(sql)
            if not r["rows"]:
                return TestResult(hyp.id, "uncertain", "no access record for this language", sql, 0)
            a = r["rows"][0]
            far = int(a["travel_days"]) >= 3
            gated = bool(a["permit_required"]) and not bool(a["community_contact"])
            ok = far or gated
            why = (f"{a['travel_days']} travel days from {a['nearest_town_km']} km, permit {'required' if a['permit_required'] else 'not required'}, "
                   f"community contact {'yes' if a['community_contact'] else 'no'}")
            return TestResult(hyp.id, "support" if ok else "reject", why + (" → reachable" if not ok else " → access is the blocker"), sql, r["rows_n"], dict(a))
        if hyp.id == "no_orthography":
            sql = (f"SELECT a.orthography_exists, COALESCE(SUM(CASE WHEN r.kind = 'dictionary_entries' THEN r.amount ELSE 0 END), 0) AS entries "
                   f"FROM access a LEFT JOIN resources r ON r.glottocode = a.glottocode WHERE a.glottocode = '{g}' GROUP BY a.orthography_exists")
            r = data.run_sql(sql)
            if not r["rows"]:
                return TestResult(hyp.id, "uncertain", "no access record for this language", sql, 0)
            row = r["rows"][0]; entries = float(row["entries"]); has = bool(row["orthography_exists"])
            ok = (not has) and entries < 500
            return TestResult(hyp.id, "support" if ok else "reject",
                              f"orthography {'exists' if has else 'missing'}, {int(entries)} dictionary entries ({'enough to write' if not ok else 'nothing to write with'})",
                              sql, r["rows_n"], {"orthography_exists": has, "entries": entries})
        if hyp.id == "resources_unarchived":
            sql = (f"SELECT COUNT(*) AS n, SUM(CASE WHEN NOT open_access AND (archive IS NULL OR archive = '') THEN 1 ELSE 0 END) AS closed, "
                   f"COALESCE(SUM(CASE WHEN NOT open_access AND (archive IS NULL OR archive = '') AND kind IN ('audio_hours','video_hours') THEN amount ELSE 0 END), 0) AS closed_hours "
                   f"FROM resources WHERE glottocode = '{g}'")
            r = data.run_sql(sql); row = r["rows"][0]
            n, closed, ch = int(row["n"] or 0), int(row["closed"] or 0), float(row["closed_hours"] or 0)
            ok = n > 0 and closed > 0
            return TestResult(hyp.id, "support" if ok else "reject",
                              f"{closed} of {n} resource records are closed and unarchived ({ch:g} h of recordings nobody can reach)" if ok
                              else f"all {n} resource records are in an open archive",
                              sql, r["rows_n"], {"records": n, "closed": closed, "closed_hours": ch})
        if hyp.id == "no_active_project":
            sql = f"SELECT COUNT(*) AS live FROM projects WHERE glottocode = '{g}' AND status IN ('active', 'planned')"
            r = data.run_sql(sql); live = int(r["rows"][0]["live"] or 0)
            return TestResult(hyp.id, "support" if live == 0 else "reject",
                              f"{live} active or planned documentation project(s)" + (" — nobody is working on it" if live == 0 else ""),
                              sql, r["rows_n"], {"live_projects": live})
        return TestResult(hyp.id, "uncertain", "no test defined")

    # ---- Planner -------------------------------------------------------------------------------------------------
    def plan(self, signal, verdicts, data):
        sup = {v.hypothesis_id: v for v in verdicts if v.verdict == "support"}
        p = signal.props
        name, speakers = p["name"], int(p["speakers"])
        open_hours = float(p.get("open_hours", 0))
        hours_needed = max(0.0, TARGET_HOURS - open_hours)
        reachable = max(1, min(speakers, 10))   # at most ~10 cooperating speakers in one campaign (heuristic)
        years = round(hours_needed / (reachable * HOURS_PER_SPEAKER_YEAR), 1) if hours_needed else 0.0
        estimate = {"heuristic": True, "target_hours": TARGET_HOURS, "open_hours": open_hours, "hours_needed": hours_needed,
                    "assumed_cooperating_speakers": reachable, "hours_per_speaker_year": HOURS_PER_SPEAKER_YEAR, "field_years": years}
        acts: list[Action] = []
        pri = 1
        if "unreachable_speakers" in sup:
            a = sup["unreachable_speakers"].data
            how = "a permit and a community contact" if a.get("permit_required") and not a.get("community_contact") else f"{a.get('travel_days')}-day field access"
            acts.append(Action(f"{signal.id}-access", f"Negotiate access for {name}: arrange {how} before any recording",
                               pri, sup["unreachable_speakers"].reason, {"recoverable_estimate": estimate})); pri += 1
        if "no_recordings" in sup:
            acts.append(Action(f"{signal.id}-record", f"Fund rapid audio documentation of {name} (~{speakers} speakers, target {TARGET_HOURS} h, ≈{years} field years)",
                               pri, sup["no_recordings"].reason, {"recoverable_estimate": estimate})); pri += 1
        if "resources_unarchived" in sup:
            d = sup["resources_unarchived"].data
            acts.append(Action(f"{signal.id}-deposit", f"Deposit the existing {d.get('closed_hours', 0):g} h of {name} recordings in an open archive (ELAR / PARADISEC)",
                               pri, sup["resources_unarchived"].reason, {"recoverable_estimate": estimate})); pri += 1
        if "no_orthography" in sup:
            acts.append(Action(f"{signal.id}-orth", f"Develop a practical orthography for {name} with its speakers",
                               pri, sup["no_orthography"].reason)); pri += 1
        if "no_active_project" in sup:
            acts.append(Action(f"{signal.id}-project", f"Open a documentation call / assign a linguist for {name}",
                               pri, sup["no_active_project"].reason, {"recoverable_estimate": estimate})); pri += 1
        if not acts:
            acts.append(Action(f"{signal.id}-watch", f"Watch {name}: documentation adequate for now, re-check speaker count yearly",
                               1, "no documentation blocker supported by the registers", {"recoverable_estimate": estimate}))
        return acts

    def explain_prompt(self, signal, verdicts, actions):
        sys_ = ("You explain language-documentation triage to a funder in plain words, at most 120 words. Use only the facts given. "
                "Say clearly that the community decides and that figures marked heuristic are estimates.")
        p = signal.props
        lines = [f"Language: {p['name']} ({p['country']}), ~{int(p['speakers'])} speakers (as of {p['speakers_year']}), median age {int(p['median_speaker_age'])}, "
                 f"endangerment {p['endangerment']}, {float(p.get('open_hours', 0)):g} h open recordings. Urgency score {signal.score}."]
        for v in verdicts:
            lines.append(f"- {v.hypothesis_id}: {v.verdict.upper()} — {v.reason}")
        lines.append("Draft actions: " + "; ".join(f"{a.priority}. {a.label}" for a in actions))
        return sys_, "\n".join(lines)

    def extra_json(self, data):
        return {"center": [0, 20], "zoom": 2}


DOMAIN = LastSpeakersDomain()
