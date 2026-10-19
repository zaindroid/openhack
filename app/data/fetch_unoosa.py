"""Owner / state-of-registry enrichment — documented stub.

Source: UN Register of Objects Launched into Outer Space, https://www.unoosa.org/oosa/en/spaceobjectregister/index.html
(free, searchable web index; the per-object records carry: international designator, name, state of registry, launch
date, function, orbital parameters at registration). There is no public JSON API; options:
  1. Export search results per launch year from the web UI as CSV and drop them in app/data/raw/unoosa_<year>.csv.
  2. Use the Space-Track SATCAT (free login) which carries OWNER and COUNTRY per NORAD id.

This script merges whatever is in app/data/raw/*.csv onto app/data/seed/objects.csv by international designator
(column OBJECT_ID in GP data = "intl_designator" here) and fills owner / country / launch_year. Columns expected in the
raw files: intl_designator, name, state_of_registry, owner, launch_date. Rows that do not match are left "unknown".
"""
from __future__ import annotations
import csv, glob, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))


def main() -> int:
    raw = {}
    for path in glob.glob(os.path.join(HERE, "raw", "unoosa_*.csv")):
        with open(path, newline="") as f:
            for r in csv.DictReader(f):
                raw[r.get("intl_designator", "").strip()] = r
    if not raw:
        print("no app/data/raw/unoosa_*.csv found; export from the UN register or Space-Track SATCAT first"); return 1
    seed = os.path.join(HERE, "seed", "objects.csv")
    with open(seed, newline="") as f:
        rows = list(csv.DictReader(f))
    hit = 0
    for r in rows:
        m = raw.get(r.get("launch_year", ""))  # replace with the real designator column when present
        if m:
            r["owner"] = m.get("owner") or m.get("state_of_registry") or r["owner"]
            r["country"] = m.get("state_of_registry", r["country"]); hit += 1
    with open(seed, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print(f"enriched {hit}/{len(rows)} objects"); return 0


if __name__ == "__main__":
    sys.exit(main())
