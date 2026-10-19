"""Dissent — when official numbers disagree about the same fact.

Signal     : one (indicator, country, year) where the latest figures from ≥2 official sources differ by more than the
             indicator's tolerance. The two figures furthest apart are "hi" and "lo".
Hypotheses : why they differ — definition_difference | base_year_or_revision | unit_or_scale | coverage_difference |
             reporting_lag | unexplained.
Tests      : deterministic, from `definitions`, `definition_tokens` and `series` (SQL attached). `unexplained` is
             supported only when every other hypothesis is rejected, so the Skeptic always rejects something.
Plan       : which figure to use for a decision, the footnote to attach, and whom to ask when nothing explains it.
Memory key : (indicator, lo source, hi source) — a rejection learned for one source pair carries over to other
             countries and years of the same pair, not to other pairs.
"""
from __future__ import annotations
from datetime import date, datetime
from whycore.domain import Action, Domain, Hypothesis, Signal, TestResult

SOURCE_LABEL = {"eurostat": "Eurostat", "worldbank": "World Bank", "un": "UN", "national": "national office"}
INTERNATIONAL = ("eurostat", "worldbank", "un")

# (unit_a, unit_b) -> how to express a value in unit_a as unit_b, given the country population for that year
# per-capita tonnes × population / 1000 = kilotonnes
CONVERSIONS = {("t_per_capita", "kt"): lambda v, pop: v * pop / 1000.0,
               ("kt", "t_per_capita"): lambda v, pop: v * 1000.0 / pop,
               ("thousand_persons", "persons"): lambda v, pop: v * 1000.0,
               ("persons", "thousand_persons"): lambda v, pop: v / 1000.0}

LATEST = """WITH latest AS (
  SELECT s.* FROM series s
  JOIN (SELECT indicator, country, year, source, MAX(vintage_date) AS v FROM series GROUP BY indicator, country, year, source) m
    ON s.indicator = m.indicator AND s.country = m.country AND s.year = m.year AND s.source = m.source AND s.vintage_date = m.v
)"""

DISAGREEMENTS_SQL = LATEST + """,
agg AS (
  SELECT indicator, country, year, COUNT(*) AS n_sources, MAX(value) AS vmax, MIN(value) AS vmin, AVG(value) AS vmean
  FROM latest GROUP BY indicator, country, year HAVING COUNT(*) >= 2
)
SELECT a.indicator, i.label, a.country, a.year, a.n_sources, a.vmax, a.vmin,
       100.0 * (a.vmax - a.vmin) / ABS(a.vmean) AS spread_pct, i.tolerance_pct, i.weight
FROM agg a JOIN indicators i ON i.indicator = a.indicator
WHERE 100.0 * (a.vmax - a.vmin) / ABS(a.vmean) > i.tolerance_pct AND (a.vmax - a.vmin) >= i.min_abs_gap
ORDER BY 100.0 * (a.vmax - a.vmin) / ABS(a.vmean) * i.weight DESC"""


def _d(v) -> date | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


def _f(v, nd=2) -> str:
    v = float(v)
    return f"{v:,.0f}" if abs(v) >= 10000 else f"{v:.{nd}f}"


class DissentDomain(Domain):
    name = "dissent"
    title = "Dissent · when official numbers disagree"
    track = "02"
    question = ("Where do Eurostat, the World Bank, the UN and national offices disagree about the same fact, why, "
                "and which figure should a decision use?")
    description = ("Illustrative seed series for six countries, five indicators and three years, built from real "
                   "definitional differences (ILO vs registered unemployment, constant vs current prices, overseas "
                   "coverage, per-capita vs total, vintage revisions, provisional estimates). Run app/data/fetch_*.py "
                   "for live figures.")
    views = {
        "disagreements": DISAGREEMENTS_SQL,
        "definitions": "SELECT definition_id, source, indicator, definition_text, base_year, coverage_note, revision_policy FROM definitions ORDER BY indicator, source",
        "sources_coverage": ("SELECT source, indicator, COUNT(DISTINCT country) AS countries, MIN(year) AS first_year, MAX(year) AS last_year, "
                             "COUNT(*) AS rows_n FROM series GROUP BY source, indicator ORDER BY indicator, source"),
    }
    sources = [
        {"name": "Eurostat JSON-stat API", "url": "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/", "access": "free, no key", "status": "fetcher ready; seed is illustrative"},
        {"name": "World Bank API v2", "url": "https://api.worldbank.org/v2/", "access": "free, no key", "status": "fetcher ready; seed is illustrative"},
        {"name": "UN SDG API / UNdata", "url": "https://unstats.un.org/sdgapi/v1/sdg/", "access": "free, no key", "status": "fetcher ready; seed is illustrative"},
        {"name": "National offices (Destatis GENESIS, INSEE, INE, ISTAT, CBS, GUS)", "url": "https://www-genesis.destatis.de", "access": "free, some need registration", "status": "manual / per-office adapters; seed is illustrative"},
    ]

    # ---- Scout ----------------------------------------------------------------------------------------------------
    def scout(self, data, limit):
        res = data.run_sql(DISAGREEMENTS_SQL)
        out = []
        for r in res["rows"][:limit]:
            pair_sql = LATEST + (f" SELECT source, value, unit, vintage_date, definition_id FROM latest WHERE indicator = '{r['indicator']}' "
                                 f"AND country = '{r['country']}' AND year = {int(r['year'])} ORDER BY value DESC, source")
            rows = data.run_sql(pair_sql)["rows"]
            hi, lo = rows[0], rows[-1]
            spread = float(r["spread_pct"])
            label = (f"{r['label']} {r['country']} {int(r['year'])}: {SOURCE_LABEL[hi['source']]} {_f(hi['value'])} {hi['unit']} vs "
                     f"{SOURCE_LABEL[lo['source']]} {_f(lo['value'])} {lo['unit']} (spread {spread:.0f}%)")
            props = {"indicator": r["indicator"], "indicator_label": r["label"], "country": r["country"], "year": int(r["year"]),
                     "n_sources": int(r["n_sources"]), "spread_pct": round(spread, 1), "tolerance_pct": float(r["tolerance_pct"]),
                     "src_hi": hi["source"], "val_hi": float(hi["value"]), "unit_hi": hi["unit"], "def_hi": hi["definition_id"], "vintage_hi": str(_d(hi["vintage_date"])),
                     "src_lo": lo["source"], "val_lo": float(lo["value"]), "unit_lo": lo["unit"], "def_lo": lo["definition_id"], "vintage_lo": str(_d(lo["vintage_date"])),
                     "memory_key": f"{r['indicator']}|{lo['source']}|{hi['source']}"}
            sid = f"{r['indicator']}-{r['country']}-{int(r['year'])}"
            out.append(Signal(id=sid, label=label, score=round(spread * float(r["weight"]), 2), props=props, sql=pair_sql, rows=len(rows)))
        return out

    # ---- Investigator ---------------------------------------------------------------------------------------------
    def hypotheses(self, signal, data):
        return [Hypothesis("definition_difference", "The two sources define the indicator differently"),
                Hypothesis("base_year_or_revision", "Different base year or vintage: one figure was revised later"),
                Hypothesis("unit_or_scale", "Different unit or scale (per capita vs total, thousands vs units)"),
                Hypothesis("coverage_difference", "Different territorial or population coverage"),
                Hypothesis("reporting_lag", "One figure is a provisional estimate"),
                Hypothesis("unexplained", "No documented reason: the sources should be asked")]

    # ---- Skeptic --------------------------------------------------------------------------------------------------
    def _tokens(self, data, def_id: str, kind: str):
        sql = f"SELECT token FROM definition_tokens WHERE definition_id = '{def_id}' AND kind = '{kind}' ORDER BY token"
        r = data.run_sql(sql)
        return {row["token"] for row in r["rows"]}, sql, r["rows_n"]

    def _defs(self, data, p):
        sql = f"SELECT definition_id, source, base_year, coverage_note, revision_policy FROM definitions WHERE definition_id IN ('{p['def_hi']}', '{p['def_lo']}')"
        r = data.run_sql(sql)
        by = {row["definition_id"]: row for row in r["rows"]}
        return by.get(p["def_hi"], {}), by.get(p["def_lo"], {}), sql, r["rows_n"]

    def test(self, signal, hyp, data):
        p = signal.props
        H, L = SOURCE_LABEL[p["src_hi"]], SOURCE_LABEL[p["src_lo"]]
        if hyp.id == "definition_difference":
            th, sql, n1 = self._tokens(data, p["def_hi"], "definition")
            tl, _, n2 = self._tokens(data, p["def_lo"], "definition")
            diff = th ^ tl
            if diff:
                return TestResult(hyp.id, "support", f"{H} defines it by {{{', '.join(sorted(th)) or '—'}}}, {L} by {{{', '.join(sorted(tl)) or '—'}}}: "
                                  f"{len(diff)} differing definition term(s)", sql, n1 + n2, {"hi": sorted(th), "lo": sorted(tl)})
            return TestResult(hyp.id, "reject", f"both sources use the same definition terms {{{', '.join(sorted(th)) or '—'}}}", sql, n1 + n2, {"shared": sorted(th)})

        if hyp.id == "base_year_or_revision":
            dh, dl, sql, n = self._defs(data, p)
            bh, bl = (dh.get("base_year") or ""), (dl.get("base_year") or "")
            if str(bh) != str(bl) and bh and bl:
                return TestResult(hyp.id, "support", f"base years differ: {H} {bh} vs {L} {bl}", sql, n, {"base_hi": bh, "base_lo": bl})
            vh, vl = _d(p["vintage_hi"]), _d(p["vintage_lo"])
            gap = abs((vh - vl).days) if vh and vl else 0
            if gap > 180:
                nsql = (f"SELECT vintage_date, value FROM series WHERE indicator = '{p['indicator']}' AND country = '{p['country']}' "
                        f"AND year = {p['year']} AND source = 'national' ORDER BY vintage_date")
                nr = data.run_sql(nsql)
                vals = [float(r["value"]) for r in nr["rows"]]
                moved = (max(vals) - min(vals)) if len(vals) >= 2 else 0.0
                spread_abs = abs(p["val_hi"] - p["val_lo"])
                if len(vals) >= 2 and moved >= 0.5 * spread_abs:
                    return TestResult(hyp.id, "support", f"vintages {gap} days apart ({L} {p['vintage_lo']}, {H} {p['vintage_hi']}) and the national "
                                      f"series was revised by {moved:.2f} between its {len(vals)} vintages (spread is {spread_abs:.2f}): the older figure predates a revision",
                                      nsql, nr["rows_n"], {"gap_days": gap, "national_vintages": vals})
                return TestResult(hyp.id, "reject", f"vintages {gap} days apart but no revision moved the national figure (vintages: {vals or 'one only'})", nsql, nr["rows_n"], {"gap_days": gap})
            return TestResult(hyp.id, "reject", f"same base year ({bh or 'n/a'}) and vintages only {gap} days apart", sql, n, {"gap_days": gap})

        if hyp.id == "unit_or_scale":
            if p["unit_hi"] == p["unit_lo"]:
                return TestResult(hyp.id, "reject", f"same unit ({p['unit_hi']}) in both sources", signal.sql, signal.rows, {})
            conv = CONVERSIONS.get((p["unit_hi"], p["unit_lo"]))
            psql = LATEST + f" SELECT AVG(value) AS pop FROM latest WHERE indicator = 'population' AND country = '{p['country']}' AND year = {p['year']}"
            pr = data.run_sql(psql)
            pop = pr["rows"][0]["pop"] if pr["rows"] and pr["rows"][0]["pop"] is not None else None
            if conv is None or pop is None:
                return TestResult(hyp.id, "uncertain", f"units differ ({p['unit_hi']} vs {p['unit_lo']}) but no conversion available", psql, pr["rows_n"], {})
            converted = conv(p["val_hi"], float(pop))
            residual = abs(converted - p["val_lo"]) / max(abs(p["val_lo"]), 1e-9) * 100
            verdict = "support" if residual < p["tolerance_pct"] else "reject"
            return TestResult(hyp.id, verdict, f"{H} {_f(p['val_hi'])} {p['unit_hi']} × population {_f(pop)} = {_f(converted)} {p['unit_lo']} vs {L} {_f(p['val_lo'])} {p['unit_lo']}: "
                              f"residual {residual:.1f}% ({'within' if verdict == 'support' else 'outside'} tolerance {p['tolerance_pct']:.0f}%)", psql, pr["rows_n"],
                              {"converted": converted, "residual_pct": residual})

        if hyp.id == "coverage_difference":
            th, sql, n1 = self._tokens(data, p["def_hi"], "coverage")
            tl, _, n2 = self._tokens(data, p["def_lo"], "coverage")
            if th ^ tl:
                dh, dl, _, _ = self._defs(data, p)
                return TestResult(hyp.id, "support", f"coverage differs: {H} “{dh.get('coverage_note')}” vs {L} “{dl.get('coverage_note')}”", sql, n1 + n2, {"hi": sorted(th), "lo": sorted(tl)})
            return TestResult(hyp.id, "reject", f"same coverage terms {{{', '.join(sorted(th)) or '—'}}}", sql, n1 + n2, {})

        if hyp.id == "reporting_lag":
            th, sql, n1 = self._tokens(data, p["def_hi"], "status")
            tl, _, n2 = self._tokens(data, p["def_lo"], "status")
            ph, pl = "provisional" in th, "provisional" in tl
            if ph != pl:
                who = H if ph else L
                return TestResult(hyp.id, "support", f"{who} publishes a provisional estimate for {p['year']}; the other figure is final", sql, n1 + n2, {"provisional": who})
            return TestResult(hyp.id, "reject", "neither figure is flagged provisional" if not ph else "both figures are provisional", sql, n1 + n2, {})

        if hyp.id == "unexplained":
            others = [h for h in self.hypotheses(signal, data) if h.id != "unexplained"]
            results = [self.test(signal, h, data) for h in others]
            rejected = [r for r in results if r.verdict == "reject"]
            sql = "SELECT COUNT(*) AS n FROM definitions WHERE definition_id IN ('%s', '%s')" % (p["def_hi"], p["def_lo"])
            n = data.run_sql(sql)["rows_n"]
            if len(rejected) == len(results):
                return TestResult(hyp.id, "support", f"all {len(results)} documented explanations rejected: same definition terms, unit, coverage, vintage and status", sql, n,
                                  {"rejected": [r.hypothesis_id for r in rejected]})
            explained = [r.hypothesis_id for r in results if r.verdict == "support"]
            return TestResult(hyp.id, "reject", f"explained by {', '.join(explained) or 'an uncertain test'}", sql, n, {"explained": explained})

        return TestResult(hyp.id, "uncertain", "unknown hypothesis")

    # ---- Planner --------------------------------------------------------------------------------------------------
    def plan(self, signal, verdicts, data):
        p = signal.props
        sup = {v.hypothesis_id: v for v in verdicts if v.verdict == "support"}
        H, L = SOURCE_LABEL[p["src_hi"]], SOURCE_LABEL[p["src_lo"]]
        sid = signal.id
        acts = []

        def use(src, val, unit, why):
            acts.append(Action(f"{sid}-use", f"Use the {SOURCE_LABEL[src]} figure: {_f(val)} {unit}", 1, why, {"source": src, "value": val, "unit": unit}))

        if "reporting_lag" in sup:
            prov = sup["reporting_lag"].data.get("provisional")
            src = p["src_lo"] if prov == H else p["src_hi"]
            use(src, p["val_lo"] if src == p["src_lo"] else p["val_hi"], p["unit_lo"] if src == p["src_lo"] else p["unit_hi"], "the other figure is a provisional estimate")
        elif "base_year_or_revision" in sup:
            newer = p["src_hi"] if (_d(p["vintage_hi"]) or date.min) >= (_d(p["vintage_lo"]) or date.min) else p["src_lo"]
            use(newer, p["val_hi"] if newer == p["src_hi"] else p["val_lo"], p["unit_hi"] if newer == p["src_hi"] else p["unit_lo"], "most recent vintage, after the national revision")
        elif "unit_or_scale" in sup:
            acts.append(Action(f"{sid}-use", f"Both figures agree once converted: {_f(p['val_hi'])} {p['unit_hi']} ≈ {_f(sup['unit_or_scale'].data.get('converted', 0))} {p['unit_lo']}", 1,
                               "no real disagreement; pick the unit the decision needs", {"converted": sup["unit_or_scale"].data}))
        elif "definition_difference" in sup or "coverage_difference" in sup:
            intl = [s for s in (p["src_hi"], p["src_lo"]) if s in INTERNATIONAL]
            src = intl[0] if intl else p["src_hi"]
            val = p["val_hi"] if src == p["src_hi"] else p["val_lo"]
            unit = p["unit_hi"] if src == p["src_hi"] else p["unit_lo"]
            why = ("internationally comparable definition; use the national figure only for a domestic administrative purpose"
                   if "definition_difference" in sup else "broader territorial coverage; use the narrower figure only for a regional decision")
            use(src, val, unit, why)
        else:
            acts.append(Action(f"{sid}-use", f"Use the mean ({_f((p['val_hi'] + p['val_lo']) / 2)} {p['unit_lo']}) with a range {_f(p['val_lo'])}–{_f(p['val_hi'])}", 1,
                               "no documented explanation; the range is the honest number", {}))
        reasons = "; ".join(f"{v.hypothesis_id.replace('_', ' ')}: {v.reason}" for v in verdicts if v.verdict == "support") or "unexplained"
        acts.append(Action(f"{sid}-footnote", f"Footnote: {H} and {L} differ by {p['spread_pct']:.0f}% for {p['indicator_label']} {p['country']} {p['year']} — {reasons[:220]}", 2,
                           "every decision document should carry the disagreement, not hide it", {"footnote": reasons}))
        if "unexplained" in sup:
            acts.append(Action(f"{sid}-ask", f"Ask {H} and {L} why {p['indicator_label']} {p['country']} {p['year']} differs ({_f(p['val_hi'])} vs {_f(p['val_lo'])})", 3,
                               "no definition, unit, coverage, vintage or status difference on record", {"to": [p["src_hi"], p["src_lo"]]}))
        return acts

    def explain_prompt(self, signal, verdicts, actions):
        sys_ = ("You explain disagreements between official statistics to a policy analyst in plain language, at most 120 words. "
                "Use only the facts and numbers given. Name the sources. End with which figure to use and why.")
        p = signal.props
        lines = [f"Disagreement: {signal.label}", f"Sources: {SOURCE_LABEL[p['src_hi']]} ({p['vintage_hi']}) vs {SOURCE_LABEL[p['src_lo']]} ({p['vintage_lo']})"]
        lines += [f"- {v.hypothesis_id}: {v.verdict.upper()} — {v.reason}" for v in verdicts]
        lines.append("Actions (drafts): " + "; ".join(f"{a.priority}. {a.label}" for a in actions))
        return sys_, "\n".join(lines)

    def extra_json(self, data):
        return {"center": [50.0, 10.0], "zoom": 4}


DOMAIN = DissentDomain()
