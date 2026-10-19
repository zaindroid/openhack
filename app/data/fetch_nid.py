"""Map a National Inventory of Dams export to app/data/seed/dams.csv.

The NID portal (https://nid.sec.usace.army.mil) offers a free CSV download per state ("Download" → CSV) after an
interactive click; there is no stable unauthenticated URL, so this script converts a file you downloaded:
    python app/data/fetch_nid.py --csv ~/Downloads/nid_PA.csv [--out app/data/seed/dams.csv]
Columns used (NID names vary slightly by export; adjust COLS if yours differ):
    NID ID → dam_id · Dam Name → name · Latitude/Longitude → lat/lon · Year Completed → year_completed
    Hazard Potential Classification (High/Significant/Low) → hazard_class · Condition Assessment → condition
    Last Inspection Date → last_inspection · EAP Prepared (Yes/No) → eap_present
    Population at risk is NOT in the public export for high-hazard dams; set population_downstream from your own estimate
    (GHSL / census grid within the inundation zone) and say so; the seed value is illustrative.
"""
from __future__ import annotations
import argparse, csv, sys

COLS = {"dam_id": "NID ID", "name": "Dam Name", "lat": "Latitude", "lon": "Longitude", "year_completed": "Year Completed",
        "hazard_class": "Hazard Potential Classification", "condition": "Condition Assessment", "last_inspection": "Last Inspection Date",
        "eap_present": "EAP Prepared"}


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--csv", required=True); ap.add_argument("--out", default="app/data/seed/dams.csv")
    a = ap.parse_args()
    out = []
    with open(a.csv, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            try:
                out.append(dict(
                    dam_id=r[COLS["dam_id"]].strip(), name=r[COLS["name"]].strip(), lat=float(r[COLS["lat"]]), lon=float(r[COLS["lon"]]),
                    year_completed=int(float(r[COLS["year_completed"]] or 0)) or "", hazard_class=(r[COLS["hazard_class"]] or "").strip().lower(),
                    condition=(r[COLS["condition"]] or "not rated").strip().lower(), last_inspection=(r[COLS["last_inspection"]] or "")[:10],
                    population_downstream="", eap_present=str((r[COLS["eap_present"]] or "").strip().lower() in ("yes", "y", "true")).lower(),
                    replacement_cost_usd=""))
            except (KeyError, ValueError) as e:
                print("skip row:", e, file=sys.stderr)
    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys())); w.writeheader(); w.writerows(out)
    print(f"wrote {len(out)} dams to {a.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
