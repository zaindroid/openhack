# Seed data — ILLUSTRATIVE

These CSVs are illustrative. Values are in the right ballpark for 2022–2024 and the *mechanisms* of disagreement are real
(registered vs ILO unemployment in Germany, nominal vs real GDP growth, INSEE's metropolitan-only population vs
Eurostat/UN including overseas departments, per-capita vs total CO2, vintage revisions, provisional CPI estimates), but no
figure here should be quoted. Replace with real extracts:

    python app/data/fetch_eurostat.py   # → series rows with source=eurostat
    python app/data/fetch_worldbank.py  # → source=worldbank
    python app/data/fetch_un.py         # → source=un
    # national offices: per-office adapters (Destatis GENESIS, INSEE, INE, ISTAT, CBS, GUS)

Tables
- indicators.csv        indicator, label, unit_default, tolerance_pct (relative spread that counts), min_abs_gap (absolute gap that counts, so 0.1 vs 0.2 growth is not a disagreement), weight
- series.csv            indicator, country, year, source, value, unit, fetched, vintage_date, definition_id — several
                        vintages per source are allowed; the scout uses the latest vintage per source
- definitions.csv       one row per (source, indicator) definition: text, base_year, coverage_note, revision_policy
- definition_tokens.csv normalised tokens per definition, kind = definition | coverage | status; the Skeptic compares these,
                        not free text
