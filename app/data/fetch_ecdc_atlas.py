"""ECDC Surveillance Atlas (EARS-Net) → app/data/seed/resistance.csv

The Atlas (https://atlas.ecdc.europa.eu/public/index.aspx) has no documented public JSON API; the stable path is the
CSV export button on an indicator view. Export flow (once per pathogen / antimicrobial group):
  1. Disease: "Antimicrobial resistance" → Population: e.g. "Escherichia coli" → Indicator:
     "R - resistant isolates, percentage" AND "Number of isolates tested" for the antimicrobial group
     (third-generation cephalosporins, fluoroquinolones, carbapenems).
  2. Time: all years, Region: all EU/EEA countries → "Export" → CSV.
  3. Save under app/data/raw/ecdc/*.csv and run:
        python3 app/data/fetch_ecdc_atlas.py app/data/raw/ecdc/*.csv
This script parses those exports (wide or long) and writes the seed schema. If ECDC publishes a JSON endpoint for the
Atlas, add it to fetch() below — the mapping stays the same.
"""
from __future__ import annotations
import csv, glob, os, re, sys

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed", "resistance.csv")
CLASS_MAP = {"third-generation cephalosporins": "cephalosporins_3g", "3rd gen. cephalosporins": "cephalosporins_3g",
             "fluoroquinolones": "fluoroquinolones", "carbapenems": "carbapenems"}
ISO2 = {"Austria": "AT", "Belgium": "BE", "Bulgaria": "BG", "Croatia": "HR", "Cyprus": "CY", "Czechia": "CZ", "Denmark": "DK",
        "Estonia": "EE", "Finland": "FI", "France": "FR", "Germany": "DE", "Greece": "EL", "Hungary": "HU", "Iceland": "IS",
        "Ireland": "IE", "Italy": "IT", "Latvia": "LV", "Lithuania": "LT", "Luxembourg": "LU", "Malta": "MT", "Netherlands": "NL",
        "Norway": "NO", "Poland": "PL", "Portugal": "PT", "Romania": "RO", "Slovakia": "SK", "Slovenia": "SI", "Spain": "ES", "Sweden": "SE"}


def norm_class(indicator: str) -> str | None:
    low = indicator.lower()
    for k, v in CLASS_MAP.items():
        if k in low:
            return v
    return None


def parse(path: str) -> dict[tuple, dict]:
    """Returns {(country, pathogen, class, year): {resistant_pct, n_isolates, setting}} from one Atlas export."""
    rows: dict[tuple, dict] = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        rd = csv.DictReader(f)
        for r in rd:
            country = ISO2.get(r.get("RegionName", "").strip(), r.get("RegionCode", "").strip())
            pathogen = r.get("Population", "").strip()
            cls = norm_class(r.get("Indicator", ""))
            year = re.sub(r"\D", "", r.get("Time", ""))[:4]
            if not (country and pathogen and cls and year):
                continue
            key = (country, pathogen, cls, int(year))
            rec = rows.setdefault(key, {"resistant_pct": None, "n_isolates": None, "setting": "hospital"})  # EARS-Net = invasive isolates
            val = r.get("NumValue", "").replace(",", ".").strip()
            if not val or val in ("-", "NA"):
                continue
            ind = r["Indicator"].lower()
            if "percentage" in ind or ind.startswith("r "):
                rec["resistant_pct"] = float(val)
            elif "number" in ind or "isolates tested" in ind:
                rec["n_isolates"] = int(float(val))
    return rows


def main(paths: list[str]) -> None:
    files = [p for pat in paths for p in glob.glob(pat)] or glob.glob(os.path.join(os.path.dirname(OUT), "..", "raw", "ecdc", "*.csv"))
    if not files:
        sys.exit("no ECDC export CSVs given; see the module docstring for the export flow")
    merged: dict[tuple, dict] = {}
    for p in files:
        for k, v in parse(p).items():
            cur = merged.setdefault(k, {"resistant_pct": None, "n_isolates": None, "setting": v["setting"]})
            cur.update({kk: vv for kk, vv in v.items() if vv is not None})
    with open(OUT, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["country", "pathogen", "antibiotic_class", "year", "resistant_pct", "n_isolates", "setting"])
        for (c, p, k, y), v in sorted(merged.items()):
            if v["resistant_pct"] is None:
                continue
            w.writerow([c, p, k, y, v["resistant_pct"], v["n_isolates"] or "", v["setting"]])
    print(f"wrote {OUT}: {len(merged)} (country, pathogen, class, year) rows from {len(files)} files — REAL data, update seed/README.md")


if __name__ == "__main__":
    main(sys.argv[1:])
