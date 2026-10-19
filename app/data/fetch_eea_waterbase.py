"""Real fetcher: EEA Waterbase / WISE-6 disaggregated water-quality data → app/data/seed/measurements.csv (same columns).

The EEA publishes Waterbase as very large CSVs (gigabytes) behind versioned download links on
https://www.eea.europa.eu/data-and-maps/data/waterbase-water-quality-icm . The link changes per release, so pass it in.
This script streams the file and keeps only the monitoring sites you list (Mar Menor lagoon and Rambla del Albujón sites
use ES-prefixed WISE identifiers; find them in the Waterbase_*_Spatial file or on the CHS portal).

Usage:
  python app/data/fetch_eea_waterbase.py --url <Waterbase_vYYYY_T_WISE6_DisaggregatedData.csv URL or local path> \
      --sites ES070MSPFxxxx=LG1 ES070MSPFyyyy=IN1 --out app/data/seed/measurements.csv
Parameter mapping (WISE observedPropertyDeterminandLabel → our parameter):
  "Nitrate" → nitrate_mg_l · "Chlorophyll a" → chlorophyll_ug_l · "Dissolved oxygen" → dissolved_oxygen_mg_l · "Salinity" → salinity
Values are averaged per month. Needs internet (or a downloaded file). Not run in this repo: the seed is illustrative.
"""
from __future__ import annotations
import argparse, csv, io, sys
from collections import defaultdict

PARAM = {"Nitrate": "nitrate_mg_l", "Chlorophyll a": "chlorophyll_ug_l", "Dissolved oxygen": "dissolved_oxygen_mg_l", "Salinity": "salinity"}


def open_source(url: str):
    if url.startswith("http"):
        import httpx
        r = httpx.get(url, timeout=600, follow_redirects=True)
        r.raise_for_status()
        return io.StringIO(r.text)
    return open(url, newline="")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--sites", nargs="+", required=True, help="WISE_site_id=our_station_id pairs")
    ap.add_argument("--out", default="app/data/seed/measurements.csv")
    a = ap.parse_args()
    sites = dict(s.split("=", 1) for s in a.sites)
    acc: dict[tuple, list[float]] = defaultdict(list)
    with open_source(a.url) as f:
        for row in csv.DictReader(f):
            sid = sites.get(row.get("monitoringSiteIdentifier", ""))
            par = PARAM.get(row.get("observedPropertyDeterminandLabel", ""))
            if not sid or not par:
                continue
            try:
                v = float(row.get("resultObservedValue") or "")
            except ValueError:
                continue
            month = (row.get("phenomenonTimeSamplingDate") or "")[:7]
            if len(month) == 7:
                acc[(sid, month + "-01", par)].append(v)
    with open(a.out, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["station_id", "date", "parameter", "value"])
        for (sid, d, par), vals in sorted(acc.items()):
            w.writerow([sid, d, par, round(sum(vals) / len(vals), 4)])
    print(f"wrote {len(acc)} monthly rows to {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
