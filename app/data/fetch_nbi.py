"""Fetch one state's National Bridge Inventory file from FHWA and map it to app/data/seed/bridges.csv.

Usage (machine with internet):
    python app/data/fetch_nbi.py --state PA --year 2024 [--counties 003,125,129] [--out app/data/seed/bridges.csv]

Source: https://www.fhwa.dot.gov/bridge/nbi/ascii.cfm  (free, no key). FHWA publishes per-state delimited files named like
    https://www.fhwa.dot.gov/bridge/nbi/2024/delimited/PA24.txt
The exact URL pattern has changed between years; if the download 404s, open the page above, copy the state link and pass --url.

NBI items used (column names in the delimited file are ITEMnn-style):
    STRUCTURE_NUMBER_008 (8)   structure id              COUNTY_CODE_003 (3)     county FIPS
    LAT_016 / LONG_017 (16/17) DDMMSSss                  YEAR_BUILT_027 (27)     year built
    YEAR_RECONSTRUCTED_106 (106)                          ADT_029 (29) / YEAR_ADT_030 (30)
    DECK_COND_058 (58) SUPERSTRUCTURE_COND_059 (59) SUBSTRUCTURE_COND_060 (60)  0-9 ratings, 'N' = not applicable
    SCOUR_CRITICAL_113 (113)   codes 0-3 = scour critical; 4-9, N, T, U otherwise
    DATE_OF_INSPECT_090 (90) MMYY, DESIGNATED_INSPECTION_FREQ_091 (91) months
    STRUCTURE_KIND_043A / TYPE_043B (43) material / design   OPR_POSTING_EVAL_041 (41) posting status (A = open, B/D/E/P = posted or restricted)
    FACILITY_CARRIED_007 (7) + FEATURES_DESC_006A (6) → a readable name
Design life is not an NBI item: we set 75 years (50 for pre-1960 steel), state it in the README, and let engineers override.
Replacement cost: items 94-96 (improvement cost, thousands of dollars) when present; else blank (the seed's column is illustrative).
"""
from __future__ import annotations
import argparse, csv, io, sys, urllib.request

COUNTY_NAMES_PA = {"003": "Allegheny", "125": "Washington", "129": "Westmoreland"}  # extend as needed or pass --county-names file


def dms_to_deg(raw: str, lon: bool = False) -> float | None:
    s = (raw or "").strip()
    if not s or set(s) <= {"0"}:
        return None
    try:
        v = int(s)
    except ValueError:
        return None
    # NBI: DDMMSSss (lat) / DDDMMSSss (lon), hundredths of seconds
    deg = v // 1_000_000; rem = v % 1_000_000
    mins = rem // 10_000; secs = (rem % 10_000) / 100.0
    d = deg + mins / 60 + secs / 3600
    return -d if lon else d


def rating(v: str) -> int | None:
    v = (v or "").strip()
    return int(v) if v.isdigit() else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default="PA"); ap.add_argument("--year", type=int, default=2024)
    ap.add_argument("--url"); ap.add_argument("--counties", default="", help="comma-separated county FIPS codes to keep")
    ap.add_argument("--out", default="app/data/seed/bridges.csv")
    a = ap.parse_args()
    url = a.url or f"https://www.fhwa.dot.gov/bridge/nbi/{a.year}/delimited/{a.state}{str(a.year)[2:]}.txt"
    print("downloading", url, file=sys.stderr)
    with urllib.request.urlopen(url, timeout=120) as r:
        text = r.read().decode("latin-1")
    rows = list(csv.DictReader(io.StringIO(text)))
    keep = set(a.counties.split(",")) if a.counties else None
    out = []
    for r in rows:
        if keep and r.get("COUNTY_CODE_003", "").strip().zfill(3) not in keep:
            continue
        d, s, b = rating(r.get("DECK_COND_058")), rating(r.get("SUPERSTRUCTURE_COND_059")), rating(r.get("SUBSTRUCTURE_COND_060"))
        if None in (d, s, b):
            continue  # culverts etc. ('N') are out of scope here
        yb = int(r.get("YEAR_BUILT_027") or 0) or None
        if not yb:
            continue
        insp = (r.get("DATE_OF_INSPECT_090") or "").strip()
        last = f"20{insp[2:]}-{insp[:2]}-01" if len(insp) == 4 and insp.isdigit() else ""
        scour = (r.get("SCOUR_CRITICAL_113") or "").strip() in {"0", "1", "2", "3"}
        posted = (r.get("OPR_POSTING_EVAL_041") or "A").strip() != "A"
        cost_k = (r.get("TOTAL_IMP_COST_096") or "").strip()
        county = COUNTY_NAMES_PA.get(r.get("COUNTY_CODE_003", "").strip().zfill(3), r.get("COUNTY_CODE_003", "").strip())
        material = "steel" if (r.get("STRUCTURE_KIND_043A") or "").strip() in {"3", "4"} else "concrete"
        out.append(dict(
            structure_id=r.get("STRUCTURE_NUMBER_008", "").strip(), name=f"{(r.get('FACILITY_CARRIED_007') or '').strip()} over {(r.get('FEATURES_DESC_006A') or '').strip()}".strip(),
            state=a.state, county=county, lat=dms_to_deg(r.get("LAT_016")), lon=dms_to_deg(r.get("LONG_017"), lon=True),
            year_built=yb, year_reconstructed=(r.get("YEAR_RECONSTRUCTED_106") or "").strip().lstrip("0") or "",
            design_life_years=50 if (yb < 1960 and material == "steel") else 75,
            deck_rating=d, superstructure_rating=s, substructure_rating=b, scour_critical=str(scour).lower(),
            adt=int(r.get("ADT_029") or 0), adt_year=int(r.get("YEAR_ADT_030") or a.year), last_inspection=last,
            inspection_interval_months=int(r.get("DESIGNATED_INSPECTION_FREQ_091") or 24), material=material,
            posted_load_limit=str(posted).lower(), replacement_cost_usd=int(cost_k) * 1000 if cost_k.isdigit() else ""))
    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys())); w.writeheader(); w.writerows(out)
    print(f"wrote {len(out)} bridges to {a.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
