"""Fetch Eurostat figures for every indicator in indicator_map.yaml and write them into seed/series.csv (source=eurostat).

API: https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{dataset}?format=JSON&geo=DE&geo=FR&time=2023&...
Free, no key. JSON-stat 2.0: `dimension.<dim>.category.index` maps codes → positions, `value` is a flat dict keyed by the
row-major position over `id`/`size`. The "updated" field is the dataset's last update, used as vintage_date.

Usage:  python app/data/fetch_eurostat.py            (needs internet; runs on your laptop or servingz, not in CI)
"""
from __future__ import annotations
import sys
import httpx
from common import ISO3, MAP, row, write_rows

BASE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"


def jsonstat_cells(js: dict) -> list[tuple[dict, float]]:
    """Expand a JSON-stat 2.0 dataset into (coords, value) pairs."""
    ids, sizes = js["id"], js["size"]
    cats = {d: {pos: code for code, pos in js["dimension"][d]["category"]["index"].items()} for d in ids}
    out = []
    for flat, val in js["value"].items():
        idx, rem = [], int(flat)
        for s in reversed(sizes):
            idx.append(rem % s); rem //= s
        idx.reverse()
        out.append(({d: cats[d][i] for d, i in zip(ids, idx)}, float(val)))
    return out


def fetch(indicator: str, spec: dict, countries: list[str], years: list[int]) -> list[dict]:
    params = [("format", "JSON"), ("lang", "EN")] + [("geo", c) for c in countries] + [("time", str(y)) for y in years]
    params += list(spec.get("filters", {}).items())
    r = httpx.get(BASE + spec["dataset"], params=params, timeout=60)
    r.raise_for_status()
    js = r.json()
    vintage = (js.get("updated") or "")[:10] or None
    unit = spec.get("unit") or MAP["indicators"][indicator].get("unit", "")
    rows = []
    for coords, val in jsonstat_cells(js):
        rows.append(row(indicator, coords["geo"], int(coords["time"]), "eurostat", val, unit, spec["definition_id"], vintage))
    return rows


def main() -> int:
    countries, years = MAP["countries"], MAP["years"]
    all_rows = []
    for ind, block in MAP["indicators"].items():
        spec = block.get("eurostat")
        if not spec or not spec.get("dataset"):
            continue
        try:
            got = fetch(ind, spec, countries, years)
            print(f"{ind}: {len(got)} rows from {spec['dataset']}")
            all_rows += got
        except Exception as e:
            print(f"{ind}: FAILED {e}", file=sys.stderr)
    if all_rows:
        print("wrote", write_rows(all_rows, replace_source="eurostat"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
