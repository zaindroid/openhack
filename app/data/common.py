"""Shared helpers for the Dissent fetchers: read indicator_map.yaml, append rows in the series schema."""
from __future__ import annotations
import csv, datetime as dt, os
import yaml

HERE = os.path.dirname(__file__)
SEED = os.path.join(HERE, "seed")
MAP = yaml.safe_load(open(os.path.join(HERE, "indicator_map.yaml")))
COLUMNS = ["indicator", "country", "year", "source", "value", "unit", "fetched", "vintage_date", "definition_id"]

# ISO2 (what we use) ↔ ISO3 (World Bank, UN)
ISO3 = {"DE": "DEU", "FR": "FRA", "ES": "ESP", "IT": "ITA", "NL": "NLD", "PL": "POL", "AT": "AUT", "BE": "BEL", "SE": "SWE", "DK": "DNK"}
ISO2 = {v: k for k, v in ISO3.items()}


def today() -> str:
    return dt.date.today().isoformat()


def write_rows(rows: list[dict], out: str | None = None, replace_source: str | None = None) -> str:
    """Append rows to seed/series.csv (default) — or, with replace_source, drop that source's old rows first so a
    re-fetch does not duplicate. Keeps every other source untouched."""
    out = out or os.path.join(SEED, "series.csv")
    existing: list[dict] = []
    if os.path.exists(out):
        with open(out, newline="") as f:
            existing = [r for r in csv.DictReader(f) if not (replace_source and r["source"] == replace_source)]
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for r in existing + rows:
            w.writerow({c: r.get(c, "") for c in COLUMNS})
    return out


def row(indicator: str, country: str, year: int, source: str, value, unit: str, definition_id: str, vintage: str | None = None) -> dict:
    return {"indicator": indicator, "country": country, "year": int(year), "source": source, "value": value, "unit": unit,
            "fetched": today(), "vintage_date": vintage or today(), "definition_id": definition_id}
