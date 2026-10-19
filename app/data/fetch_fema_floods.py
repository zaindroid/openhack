"""Count FEMA flood-related disaster declarations per county and year → app/data/seed/floods.csv.

    python app/data/fetch_fema_floods.py --state PA --counties "Allegheny,Washington,Westmoreland" --since 2015

Source: OpenFEMA Disaster Declarations Summaries v2 (free, no key)
    https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries?$filter=state eq 'PA' and declarationDate ge '2015-01-01'
Fields: designatedArea ("Allegheny (County)"), incidentType (Flood, Severe Storm(s), Hurricane...), declarationDate, disasterNumber.
We count one event per (county, year, disasterNumber) whose incidentType contains Flood, Storm or Hurricane.
"""
from __future__ import annotations
import argparse, csv, json, sys, urllib.parse, urllib.request
from collections import defaultdict

BASE = "https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries"


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--state", default="PA"); ap.add_argument("--counties", default="")
    ap.add_argument("--since", type=int, default=2015); ap.add_argument("--out", default="app/data/seed/floods.csv")
    a = ap.parse_args()
    keep = {c.strip() for c in a.counties.split(",") if c.strip()}
    counts: dict[tuple[str, int], set] = defaultdict(set)
    skip = 0
    while True:
        q = {"$filter": f"state eq '{a.state}' and declarationDate ge '{a.since}-01-01'", "$top": "1000", "$skip": str(skip),
             "$select": "designatedArea,incidentType,declarationDate,disasterNumber"}
        with urllib.request.urlopen(BASE + "?" + urllib.parse.urlencode(q), timeout=120) as r:
            js = json.load(r)
        rows = js.get("DisasterDeclarationsSummaries", [])
        for r in rows:
            county = (r.get("designatedArea") or "").replace("(County)", "").strip()
            if keep and county not in keep:
                continue
            if not any(k in (r.get("incidentType") or "") for k in ("Flood", "Storm", "Hurricane")):
                continue
            counts[(county, int(r["declarationDate"][:4]))].add(r["disasterNumber"])
        if len(rows) < 1000:
            break
        skip += 1000
    years = range(a.since, 2027)
    out = [dict(county=c, year=y, events=len(counts.get((c, y), set()))) for c in sorted({c for c, _ in counts} | keep) for y in years]
    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["county", "year", "events"]); w.writeheader(); w.writerows(out)
    print(f"wrote {len(out)} rows to {a.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
