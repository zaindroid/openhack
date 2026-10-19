"""Antibiotic Watch — which drug-bug resistance pairs are rising where, and why.

Signals  : (country, pathogen, antibiotic class) pairs whose resistant % rose ≥ 5 points over the last three years
           with ≥ 100 isolates in the latest year.
Causes   : human_prescribing · livestock_use · surveillance_artifact · importation · unexplained
Skeptic  : every verdict comes from the tables below with the SQL attached. A surveillance artifact (labs added or
           definitions changed while isolate counts jumped > 50 %) REJECTS the biological causes: a reporting change is
           not biology. 'unexplained' is supported only when every other cause was rejected.
Actions  : ministry-level drafts, approved by a human in the UI.
"""
from __future__ import annotations
import math
from whycore.domain import Action, Domain, Hypothesis, Signal, TestResult

WINDOW = 3            # years between start and end of the rise
MIN_RISE = 5.0        # percentage points
MIN_ISOLATES = 100
CONS_RISE = 10.0      # % change in DDD/1000/day that counts as a prescribing rise
LIV_RISE = 10.0       # % change in mg/PCU that counts as a livestock rise
ISO_JUMP = 50.0       # % jump in isolates that marks a reporting change
IMPORT_MIN = 30.0     # imported share % that counts as importation

CLASS_LABEL = {"cephalosporins_3g": "3rd-gen cephalosporins", "fluoroquinolones": "fluoroquinolones", "carbapenems": "carbapenems"}


def _fmt_n(n: int | float) -> str:
    return f"{int(n):,}".replace(",", " ")


def _pct_change(a: float, b: float) -> float | None:
    if a is None or b is None or a == 0:
        return None
    return round((b - a) / abs(a) * 100.0, 1)


class AntibioticWatch(Domain):
    name = "antibiotic-watch"
    title = "Antibiotic Watch · resistance explain-why"
    track = "03"
    question = "Which drug-bug pairs are rising fastest in which countries, why, and what should a health ministry watch or change first?"
    description = ("Illustrative surveillance series modelled on WHO GLASS / ECDC exports (not real figures). "
                   "Run app/data/fetch_ecdc_atlas.py for real data. Verdicts come from the numbers; the model only explains.")
    views = {
        "rising_pairs": (
            "SELECT r2.country, r2.pathogen, r2.antibiotic_class, r2.setting, r1.resistant_pct AS pct_start, "
            "r2.resistant_pct AS pct_end, r2.resistant_pct - r1.resistant_pct AS rise_points, r2.n_isolates "
            "FROM resistance r2 JOIN resistance r1 ON r1.country = r2.country AND r1.pathogen = r2.pathogen "
            "AND r1.antibiotic_class = r2.antibiotic_class AND r1.year = r2.year - 3 "
            "WHERE r2.year = (SELECT MAX(year) FROM resistance) ORDER BY r2.resistant_pct - r1.resistant_pct DESC"),
        "consumption_trends": "SELECT country, antibiotic_class, year, ddd_per_1000_per_day FROM consumption ORDER BY country, antibiotic_class, year",
        "livestock_trends": "SELECT country, antibiotic_class, year, mg_per_pcu FROM livestock_use ORDER BY country, antibiotic_class, year",
        "surveillance_changes": "SELECT country, year, change, note FROM surveillance_changes WHERE change <> 'none' ORDER BY country, year",
    }
    sources = [
        {"name": "WHO GLASS (Global Antimicrobial Resistance and Use Surveillance System)", "url": "https://www.who.int/initiatives/glass",
         "access": "dashboards + annual data downloads; no stable public API", "status": "seed is illustrative"},
        {"name": "ECDC Surveillance Atlas of Infectious Diseases", "url": "https://atlas.ecdc.europa.eu",
         "access": "CSV export per indicator (EARS-Net resistance %, isolate counts)", "status": "seed is illustrative"},
        {"name": "ECDC ESAC-Net (antimicrobial consumption, DDD/1000/day)", "url": "https://www.ecdc.europa.eu/en/antimicrobial-consumption/surveillance-and-disease-data/database",
         "access": "interactive database, CSV export", "status": "seed is illustrative"},
        {"name": "EMA ESVAC / ESUAvet (veterinary antimicrobial sales, mg/PCU)",
         "url": "https://www.ema.europa.eu/en/veterinary-regulatory-overview/antimicrobial-resistance-veterinary-medicine/european-sales-use-antimicrobials-veterinary-medicine",
         "access": "annual report tables, CSV/XLSX", "status": "seed is illustrative"},
    ]

    def __init__(self) -> None:
        self._cache: dict[str, dict[str, TestResult]] = {}

    # ---- Scout -------------------------------------------------------------------------------------------------------
    def scout(self, data, limit):
        self._cache.clear()                      # verdicts are per run; never reuse across runs
        sql = (
            "SELECT r2.country, r2.pathogen, r2.antibiotic_class, r2.setting, r1.year AS year_start, r2.year AS year_end, "
            "r1.resistant_pct AS pct_start, r2.resistant_pct AS pct_end, r2.n_isolates, r1.n_isolates AS n_start "
            "FROM resistance r2 JOIN resistance r1 ON r1.country = r2.country AND r1.pathogen = r2.pathogen "
            "AND r1.antibiotic_class = r2.antibiotic_class AND r1.setting = r2.setting AND r1.year = r2.year - %d "
            "WHERE r2.year = (SELECT MAX(year) FROM resistance) AND r2.resistant_pct - r1.resistant_pct >= %s "
            "AND r2.n_isolates >= %d ORDER BY r2.resistant_pct - r1.resistant_pct DESC" % (WINDOW, MIN_RISE, MIN_ISOLATES))
        res = data.run_sql(sql)
        out = []
        for r in res["rows"]:
            rise = float(r["pct_end"]) - float(r["pct_start"])
            sid = f"{r['country']}|{r['pathogen']}|{r['antibiotic_class']}"
            label = (f"{r['country']} · {r['pathogen']} vs {CLASS_LABEL.get(r['antibiotic_class'], r['antibiotic_class'])}: "
                     f"{float(r['pct_start']):.0f}% → {float(r['pct_end']):.0f}% ({r['year_start']}–{r['year_end']}), n={_fmt_n(r['n_isolates'])}")
            props = dict(r)
            props["rise_points"] = round(rise, 1)
            props["memory_key"] = f"{r['pathogen']}|{r['antibiotic_class']}"
            out.append(Signal(id=sid, label=label, score=round(rise * math.log(max(float(r["n_isolates"]), 2.0)), 2), props=props, sql=sql, rows=res["rows_n"]))
        return out[:limit]

    # ---- Investigator ------------------------------------------------------------------------------------------------
    def hypotheses(self, signal, data):
        cls = CLASS_LABEL.get(signal.props["antibiotic_class"], signal.props["antibiotic_class"])
        return [
            Hypothesis("human_prescribing", f"Human prescribing of {cls} rose first"),
            Hypothesis("livestock_use", f"Veterinary use of {cls} rose and the pathogen travels through the food chain"),
            Hypothesis("surveillance_artifact", "The rise is a reporting change, not biology (new labs, new definitions)"),
            Hypothesis("importation", "Imported resistant isolates (travel / cross-border care) drive the rise"),
            Hypothesis("unexplained", "None of the measured drivers explains it"),
        ]

    # ---- Skeptic -----------------------------------------------------------------------------------------------------
    def test(self, signal, hyp, data):
        cache = self._cache.setdefault(signal.id, {})
        if hyp.id in cache:
            return cache[hyp.id]
        fn = {"human_prescribing": self._t_prescribing, "livestock_use": self._t_livestock,
              "surveillance_artifact": self._t_artifact, "importation": self._t_import, "unexplained": self._t_unexplained}[hyp.id]
        v = fn(signal, data)
        cache[hyp.id] = v
        return v

    def _series(self, data, sql: str, col: str) -> tuple[dict[int, float], dict]:
        res = data.run_sql(sql)
        return {int(r["year"]): (float(r[col]) if r[col] is not None else None) for r in res["rows"]}, res

    def _t_artifact(self, s, data) -> TestResult:
        p = s.props
        y0, y1 = int(p["year_start"]), int(p["year_end"])
        sql = (f"SELECT c.year, c.change, c.note, r.n_isolates FROM surveillance_changes c JOIN resistance r "
               f"ON r.country = c.country AND r.year = c.year AND r.pathogen = '{p['pathogen']}' AND r.antibiotic_class = '{p['antibiotic_class']}' "
               f"WHERE c.country = '{p['country']}' AND c.year BETWEEN {y0} AND {y1} ORDER BY c.year")
        res = data.run_sql(sql)
        rows = res["rows"]
        iso = {int(r["year"]): float(r["n_isolates"]) for r in rows}
        changes = [r for r in rows if r["change"] != "none"]
        jump, jump_year = 0.0, None
        for y in range(y0 + 1, y1 + 1):
            if y in iso and (y - 1) in iso and iso[y - 1] > 0:
                j = (iso[y] - iso[y - 1]) / iso[y - 1] * 100
                if j > jump:
                    jump, jump_year = j, y
        if changes and jump > ISO_JUMP:
            c = changes[0]
            reason = (f"{c['change'].replace('_', ' ')} in {c['year']} and isolates jumped {jump:.0f}% in {jump_year} "
                      f"({_fmt_n(iso[jump_year - 1])} → {_fmt_n(iso[jump_year])}): the series changed, not necessarily the bacteria")
            return TestResult("surveillance_artifact", "support", reason, sql, res["rows_n"], {"change": c["change"], "year": c["year"], "isolate_jump_pct": round(jump, 1)})
        if changes:
            reason = f"{changes[0]['change'].replace('_', ' ')} in {changes[0]['year']} but isolates moved only {jump:.0f}% (threshold {ISO_JUMP:.0f}%)"
        else:
            reason = f"no surveillance change {y0}–{y1}; largest year-on-year isolate change {jump:.0f}%"
        return TestResult("surveillance_artifact", "reject", reason, sql, res["rows_n"], {"isolate_jump_pct": round(jump, 1)})

    def _artifact_blocks(self, s, data) -> TestResult | None:
        a = self._cache.setdefault(s.id, {}).get("surveillance_artifact") or self._t_artifact(s, data)
        self._cache[s.id]["surveillance_artifact"] = a
        return a if a.verdict == "support" else None

    def _best_lag(self, series: dict[int, float], y0: int, y1: int) -> tuple[int | None, float | None]:
        best_lag, best = None, None
        for lag in range(0, 3):
            a, b = series.get(y0 - lag), series.get(y1 - lag)
            ch = _pct_change(a, b)
            if ch is not None and (best is None or ch > best):
                best, best_lag = ch, lag
        return best_lag, best

    def _t_prescribing(self, s, data) -> TestResult:
        p = s.props
        y0, y1 = int(p["year_start"]), int(p["year_end"])
        sql = (f"SELECT year, ddd_per_1000_per_day FROM consumption WHERE country = '{p['country']}' "
               f"AND antibiotic_class = '{p['antibiotic_class']}' AND sector = 'human' AND year BETWEEN {y0 - 2} AND {y1} ORDER BY year")
        series, res = self._series(data, sql, "ddd_per_1000_per_day")
        lag, ch = self._best_lag(series, y0, y1)
        art = self._artifact_blocks(s, data)
        if art:
            return TestResult("human_prescribing", "reject", f"rise coincides with a reporting change ({art.data['change'].replace('_', ' ')} {art.data['year']}, isolates +{art.data['isolate_jump_pct']:.0f}%); prescribing cannot be read from this series", sql, res["rows_n"], {"consumption_change_pct": ch, "lag_years": lag})
        if ch is None:
            return TestResult("human_prescribing", "uncertain", "no consumption series for this class and country", sql, res["rows_n"])
        if ch >= CONS_RISE:
            return TestResult("human_prescribing", "support", f"human consumption of this class rose {ch:.0f}% ({series.get(y0 - lag):.2f} → {series.get(y1 - lag):.2f} DDD/1000/day) {lag} year(s) ahead of the resistance rise", sql, res["rows_n"], {"consumption_change_pct": ch, "lag_years": lag})
        return TestResult("human_prescribing", "reject", f"human consumption changed only {ch:+.0f}% over the window (threshold +{CONS_RISE:.0f}%, best lag {lag} y)", sql, res["rows_n"], {"consumption_change_pct": ch, "lag_years": lag})

    def _t_livestock(self, s, data) -> TestResult:
        p = s.props
        y0, y1 = int(p["year_start"]), int(p["year_end"])
        sql_z = f"SELECT zoonotic, note FROM pathogens WHERE pathogen = '{p['pathogen']}'"
        zres = data.run_sql(sql_z)
        zoonotic = bool(zres["rows"]) and str(zres["rows"][0]["zoonotic"]).lower() in ("true", "1", "t", "yes")
        sql = (f"SELECT year, mg_per_pcu FROM livestock_use WHERE country = '{p['country']}' "
               f"AND antibiotic_class = '{p['antibiotic_class']}' AND year BETWEEN {y0 - 2} AND {y1} ORDER BY year")
        series, res = self._series(data, sql, "mg_per_pcu")
        lag, ch = self._best_lag(series, y0, y1)
        both = sql_z + ";\n" + sql
        art = self._artifact_blocks(s, data)
        if art:
            return TestResult("livestock_use", "reject", f"rise coincides with a reporting change ({art.data['change'].replace('_', ' ')} {art.data['year']}); livestock use cannot be read from this series", both, res["rows_n"] + zres["rows_n"], {"livestock_change_pct": ch})
        if not zoonotic:
            return TestResult("livestock_use", "reject", f"{p['pathogen']} is not a food-chain pathogen in this registry ({zres['rows'][0]['note'] if zres['rows'] else 'no entry'}); veterinary use changed {ch if ch is not None else 0:+.0f}%", both, res["rows_n"] + zres["rows_n"], {"zoonotic": False, "livestock_change_pct": ch})
        if ch is None:
            return TestResult("livestock_use", "uncertain", "food-chain pathogen but no veterinary sales series for this class", both, res["rows_n"] + zres["rows_n"])
        if ch >= LIV_RISE:
            return TestResult("livestock_use", "support", f"food-chain pathogen and veterinary sales of this class rose {ch:.0f}% ({series.get(y0 - lag):.2f} → {series.get(y1 - lag):.2f} mg/PCU, lag {lag} y)", both, res["rows_n"] + zres["rows_n"], {"zoonotic": True, "livestock_change_pct": ch, "lag_years": lag})
        return TestResult("livestock_use", "reject", f"food-chain pathogen but veterinary sales changed only {ch:+.0f}% (threshold +{LIV_RISE:.0f}%)", both, res["rows_n"] + zres["rows_n"], {"zoonotic": True, "livestock_change_pct": ch})

    def _t_import(self, s, data) -> TestResult:
        p = s.props
        y0, y1 = int(p["year_start"]), int(p["year_end"])
        sql = (f"SELECT year, imported_share_pct FROM travel_import WHERE country = '{p['country']}' AND pathogen = '{p['pathogen']}' "
               f"AND year BETWEEN {y0} AND {y1} ORDER BY year")
        series, res = self._series(data, sql, "imported_share_pct")
        art = self._artifact_blocks(s, data)
        if art:
            return TestResult("importation", "reject", f"rise coincides with a reporting change ({art.data['change'].replace('_', ' ')} {art.data['year']}); importation cannot be read from this series", sql, res["rows_n"])
        if not series:
            return TestResult("importation", "uncertain", "no imported-share series for this pathogen", sql, 0)
        a, b = series.get(y0), series.get(y1)
        if b is not None and b >= IMPORT_MIN and a is not None and b > a:
            return TestResult("importation", "support", f"imported share {a:.0f}% → {b:.0f}% of isolates (threshold {IMPORT_MIN:.0f}% and rising)", sql, res["rows_n"], {"imported_start": a, "imported_end": b})
        return TestResult("importation", "reject", f"imported share {a if a is not None else 0:.0f}% → {b if b is not None else 0:.0f}% (needs ≥ {IMPORT_MIN:.0f}% and rising)", sql, res["rows_n"], {"imported_start": a, "imported_end": b})

    def _t_unexplained(self, s, data) -> TestResult:
        others = {}
        for hid, fn in (("human_prescribing", self._t_prescribing), ("livestock_use", self._t_livestock),
                        ("surveillance_artifact", self._t_artifact), ("importation", self._t_import)):
            v = self._cache.setdefault(s.id, {}).get(hid) or fn(s, data)
            self._cache[s.id][hid] = v
            others[hid] = v.verdict
        sql = "\n".join(f"-- {k}: {v}" for k, v in others.items())
        supported = [k for k, v in others.items() if v == "support"]
        uncertain = [k for k, v in others.items() if v == "uncertain"]
        if supported:
            return TestResult("unexplained", "reject", f"explained by {', '.join(supported)}", sql, 4, others)
        if uncertain:
            return TestResult("unexplained", "uncertain", f"no cause supported but {', '.join(uncertain)} could not be tested", sql, 4, others)
        return TestResult("unexplained", "support", "all four measured drivers rejected; the rise needs field investigation (strain typing, outbreak review)", sql, 4, others)

    # ---- Planner -----------------------------------------------------------------------------------------------------
    def plan(self, signal, verdicts, data):
        p = signal.props
        cls = CLASS_LABEL.get(p["antibiotic_class"], p["antibiotic_class"])
        sup = {v.hypothesis_id: v for v in verdicts if v.verdict == "support"}
        rise = p.get("rise_points", 0)
        acts: list[Action] = []
        base = signal.id.replace("|", "-").replace(" ", "_")
        if "surveillance_artifact" in sup:
            acts.append(Action(f"{base}-audit", f"Audit the {p['country']} surveillance change before acting on {p['pathogen']} vs {cls}", 1,
                               sup["surveillance_artifact"].reason, {"country": p["country"]}))
            acts.append(Action(f"{base}-restate", "Re-baseline the series from the year the network changed", 2,
                               "a +%.0f-point rise across a reporting change is not comparable year to year" % rise))
            return acts
        if "human_prescribing" in sup:
            acts.append(Action(f"{base}-steward", f"Stewardship review of {cls} prescribing in the {p['setting']} setting, {p['country']}", 1,
                               sup["human_prescribing"].reason, {"setting": p["setting"], "class": p["antibiotic_class"]}))
        if "livestock_use" in sup:
            acts.append(Action(f"{base}-vet", f"Veterinary use review for {cls} with the agriculture ministry, {p['country']}", 1 if "human_prescribing" not in sup else 2,
                               sup["livestock_use"].reason, {"class": p["antibiotic_class"]}))
        if "importation" in sup:
            acts.append(Action(f"{base}-travel", f"Travel and cross-border care screening guidance for {p['pathogen']}, {p['country']}", len(acts) + 1,
                               sup["importation"].reason))
        if "unexplained" in sup:
            acts.append(Action(f"{base}-investigate", f"Field investigation: strain typing and outbreak review for {p['pathogen']} vs {cls}, {p['country']}", 1,
                               sup["unexplained"].reason))
        if not acts:
            acts.append(Action(f"{base}-watch", f"Watch {p['pathogen']} vs {cls} in {p['country']}: no driver confirmed, some tests uncertain", 1,
                               "; ".join(f"{v.hypothesis_id}: {v.verdict}" for v in verdicts)))
        acts.append(Action(f"{base}-recheck", f"Re-check at next annual release ({int(p['year_end']) + 1} data)", len(acts) + 1,
                           f"+{rise:.0f} points over {WINDOW} years, n={_fmt_n(p['n_isolates'])}"))
        return acts


DOMAIN = AntibioticWatch()
