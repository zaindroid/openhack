"""Fetch World Bank figures for every indicator in indicator_map.yaml → seed/series.csv (source=worldbank).

API v2: https://api.worldbank.org/v2/country/DEU;FRA/indicator/SL.UEM.TOTL.ZS?format=json&date=2022:2024&per_page=1000
Free, no key. Response = [meta, rows]; paging via meta.pages. `lastupdated` in meta is the vintage_date.

Usage:  python app/data/fetch_worldbank.py
"""
from __future__ import annotations
import sys
import httpx
from common import ISO2, ISO3, MAP, row, write_rows

BASE = "https://api.worldbank.org/v2"


def fetch(indicator: str, spec: dict, countries: list[str], years: list[int]) -> list[dict]:
    iso3 = ";".join(ISO3[c] for c in countries)
    unit = spec.get("unit") or MAP["indicators"][indicator].get("unit", "")
    rows, page = [], 1
    while True:
        r = httpx.get(f"{BASE}/country/{iso3}/indicator/{spec['indicator']}",
                      params={"format": "json", "date": f"{min(years)}:{max(years)}", "per_page": 1000, "page": page}, timeout=60)
        r.raise_for_status()
        meta, data = r.json()
        vintage = (meta.get("lastupdated") or "")[:10] or None
        for d in data or []:
            if d["value"] is None:
                continue
            c = ISO2.get(d["countryiso3code"]) or d["country"]["id"]
            rows.append(row(indicator, c, int(d["date"]), "worldbank", float(d["value"]), unit, spec["definition_id"], vintage))
        if page >= int(meta.get("pages", 1)):
            break
        page += 1
    return rows


def main() -> int:
    all_rows = []
    for ind, block in MAP["indicators"].items():
        spec = block.get("worldbank")
        if not spec or not spec.get("indicator"):
            continue
        try:
            got = fetch(ind, spec, MAP["countries"], MAP["years"])
            print(f"{ind}: {len(got)} rows from {spec['indicator']}")
            all_rows += got
        except Exception as e:
            print(f"{ind}: FAILED {e}", file=sys.stderr)
    if all_rows:
        print("wrote", write_rows(all_rows, replace_source="worldbank"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
