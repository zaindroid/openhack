"""Fetch UN figures → seed/series.csv (source=un).

Route 1 (implemented): UN SDG Global Database API, free, no key.
  GET https://unstats.un.org/sdgapi/v1/sdg/Series/Data?seriesCode=SL_TLF_UEM&geoAreaCode=276&timePeriod=2023&pageSize=1000
  geoAreaCode is the UN M49 numeric code (DE 276, FR 250, ES 724, IT 380, NL 528, PL 616). Each row carries
  `attributes.Nature` (e.g. "C" country data, "E" estimated, "M" modelled) and `timeDetail`; rows whose
  `attributes.ObservationStatus`/footnotes say provisional get the provisional definition variant.
Route 2 (documented, not automated): UNdata (https://data.un.org) for National Accounts growth and CPI, and the World
  Population Prospects CSVs (https://population.un.org/wpp/Download). Those series have `series: null` in indicator_map.yaml
  with a note; hand-download and map onto the series schema.

Usage:  python app/data/fetch_un.py
"""
from __future__ import annotations
import sys
import httpx
from common import MAP, row, write_rows

BASE = "https://unstats.un.org/sdgapi/v1/sdg"
M49 = {"DE": "276", "FR": "250", "ES": "724", "IT": "380", "NL": "528", "PL": "616", "AT": "040", "BE": "056", "SE": "752", "DK": "208"}
M49_INV = {v: k for k, v in M49.items()}


def fetch(indicator: str, spec: dict, countries: list[str], years: list[int]) -> list[dict]:
    unit = spec.get("unit") or MAP["indicators"][indicator].get("unit", "")
    params = [("seriesCode", spec["series"]), ("pageSize", 1000)] + [("geoAreaCode", M49[c]) for c in countries] + [("timePeriod", str(y)) for y in years]
    for k, v in spec.get("dimensions", {}).items():
        params.append((f"dimensions", f'[{{"name":"{k}","values":["{v}"]}}]'))
    r = httpx.get(f"{BASE}/Series/Data", params=params, timeout=60)
    r.raise_for_status()
    rows = []
    for d in r.json().get("data", []):
        if d.get("value") in (None, "", "NaN"):
            continue
        attrs = d.get("attributes") or {}
        provisional = "provisional" in str(d.get("footnotes", "")).lower() or attrs.get("ObservationStatus") in ("P", "Provisional")
        def_id = spec["definition_id"] + ("_PROV" if provisional and not spec["definition_id"].endswith("_PROV") else "")
        rows.append(row(indicator, M49_INV.get(d["geoAreaCode"], d["geoAreaCode"]), int(d["timePeriodStart"]), "un", float(d["value"]), unit, def_id))
    return rows


def main() -> int:
    all_rows = []
    for ind, block in MAP["indicators"].items():
        spec = block.get("un")
        if not spec or not spec.get("series"):
            print(f"{ind}: no SDG series — {spec.get('note') if spec else 'not mapped'}")
            continue
        try:
            got = fetch(ind, spec, MAP["countries"], MAP["years"])
            print(f"{ind}: {len(got)} rows from {spec['series']}")
            all_rows += got
        except Exception as e:
            print(f"{ind}: FAILED {e}", file=sys.stderr)
    if all_rows:
        print("wrote", write_rows(all_rows, replace_source="un"))
        print("note: a *_PROV definition_id needs a matching row in definitions.csv with a 'provisional' status token")
    return 0


if __name__ == "__main__":
    sys.exit(main())
