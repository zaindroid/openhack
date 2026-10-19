# Dissent — when official numbers disagree

**Track 02 · research agent.** Germany's unemployment rate in 2024 is 3.4 % (Eurostat) or 6.0 % (Bundesagentur).
France has 68.2 million people (Eurostat) or 65.9 million (INSEE). Germany emitted 7.9 tonnes of CO2 per head
(World Bank) or 665 000 kilotonnes (UN). All of these are "official". Dissent finds every such disagreement with one
federated query, says *why* with evidence, and tells a decision-maker which figure to use and what footnote to attach.

## Idea card
- **Problem.** The same fact differs between Eurostat, the World Bank, the UN and national offices. Analysts pick one
  number silently, or average them, and nobody downstream knows a disagreement existed.
- **Why now.** Every one of these sources now has a free JSON API; a federated query engine can hold all four in one
  SQL. The explanations are documented in metadata, so they can be tested, not guessed.
- **What it does.** Scout → the disagreements above a per-indicator tolerance. Investigator → six competing reasons.
  Skeptic → tests each against the sources' own definitions, units, coverage notes, vintages and status flags, with the
  SQL attached; `unexplained` is supported only when everything else is rejected. Planner → "use this figure",
  "footnote this", "ask these two offices".
- **Who acts.** Policy analysts, journalists, ESG reporters, anyone who has to put one number in a document.

## Run it
```bash
pip install -r requirements.txt
python -m whycore.evals app/evals.yaml        # 6/6 cases, no key, DuckDB over the seed CSVs
uvicorn whycore.app:app --port 8080           # UI; MAX_SIGNALS=6 to also surface the "unexplained" case
```

## Data
`app/data/seed/` is **illustrative** (see its README): the mechanisms are real, the figures are approximate. Real data:

| source | API | key | fetcher |
|---|---|---|---|
| Eurostat | JSON-stat, `api/dissemination/statistics/1.0/data/{dataset}` | none | `fetch_eurostat.py` |
| World Bank | API v2 `country/{iso3}/indicator/{code}` | none | `fetch_worldbank.py` |
| UN | SDG Global Database API (`unstats.un.org/sdgapi`); UNdata and WPP by download | none | `fetch_un.py` |
| national offices | Destatis GENESIS (free registration), INSEE, INE, ISTAT, CBS, GUS | varies | per-office adapters (next) |

`indicator_map.yaml` maps each indicator to each source's code and to the definition row the figures carry.
`definition_tokens.csv` is the Skeptic's vocabulary: normalised tokens per definition (`definition`, `coverage`,
`status`). Adding a source = adding its definition row and tokens.

## The six tests
| hypothesis | supported when |
|---|---|
| definition_difference | the two definitions' `definition` tokens differ (ILO vs registered; constant vs current prices) |
| base_year_or_revision | base years differ, or vintages are > 180 days apart and the national series was revised by ≥ half the spread |
| unit_or_scale | units differ and converting (per capita × population) brings the residual under the tolerance |
| coverage_difference | `coverage` tokens differ (overseas departments included vs excluded) |
| reporting_lag | exactly one figure carries a `provisional` status token |
| unexplained | all five above are rejected — the Skeptic always rejects something |

## Demo script (90 s)
1. Open the UI: the Data tab `disagreements` is one SQL over all sources — the Zetaris moment.
2. Run agent. Top card: CO2 Germany 2022, 665 000 kt vs 7.9 t per head, "spread 200 %". Skeptic: unit_or_scale
   supported — "× population 83.4 M = 7.97 t, residual 0.9 %". Action: *no real disagreement*.
3. Second card: unemployment Germany, registered vs ILO. Hover a verdict → the SQL that proved it.
4. Set `MAX_SIGNALS=6`: Netherlands unemployment, UN vs World Bank, every explanation rejected → **unexplained**,
   action 3 "Ask UN and World Bank". Approve it. Run again: warm run, remembered rejections skipped.

## Sponsor mapping
- **Zetaris** — the whole point: one SQL across four live APIs and a national table; `v_disagreements` is a semantic
  view; every verdict cites the query it ran.
- **Meterless** — routes every explanation call to Nemotron and holds the memory of rejections per
  (indicator, source pair), so run 2 is shorter; metered per app.
- **NVIDIA Nemotron** — Super for the plain-language explanation of each verdict; Nano for formatting footnotes.
- **Cursor** — the build tool; sessions logged in the repo's docs.

## Limits
- Tokens are hand-curated per definition; a real deployment derives them from the sources' metadata endpoints
  (Eurostat `metadata`, World Bank indicator `sourceNote`).
- Memory generalises a rejection across countries/years for the same (indicator, source pair), which is right for
  unit/definition/coverage reasons and approximate for vintage/provisional ones.
- "Which figure to use" is a default rule (international definition, newest vintage, final over provisional); the
  decision's purpose can override it, which is why the action stays a draft until a human approves.
