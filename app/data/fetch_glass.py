"""WHO GLASS → app/data/seed/resistance.csv (non-EU countries).

Status: documented stub. GLASS publishes dashboards (https://worldhealthorg.shinyapps.io/glass-dashboard/) and annual
data downloads (XLSX/CSV) from https://www.who.int/initiatives/glass but no stable, documented public API as of Oct 2026.
Flow:
  1. Download the latest "GLASS AMR data" file for the countries you need into app/data/raw/glass/.
  2. Run: python3 app/data/fetch_glass.py app/data/raw/glass/*.csv
Expected columns in the download (names vary by release; adjust COLS): Country (ISO3), Pathogen, Antibiotic (or class),
Year, PercentResistant (or Resistant / Tested), NumTested, Specimen or Setting.
Output appends to resistance.csv in the seed schema. Country ISO3 → ISO2 via the small table below (extend as needed).
"""
from __future__ import annotations
import csv, glob, os, sys

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed", "resistance.csv")
COLS = {"country": "Country", "pathogen": "Pathogen", "antibiotic": "Antibiotic", "year": "Year",
        "pct": "PercentResistant", "n": "NumTested", "setting": "Setting"}
ISO3_TO_2 = {"DEU": "DE", "FRA": "FR", "ITA": "IT", "ESP": "ES", "NLD": "NL", "POL": "PL", "IND": "IN", "BRA": "BR", "ZAF": "ZA",
             "EGY": "EG", "PAK": "PK", "NGA": "NG", "USA": "US", "GBR": "UK", "TUR": "TR", "IRN": "IR", "KEN": "KE", "THA": "TH"}
CLASS_MAP = {"ceftriaxone": "cephalosporins_3g", "cefotaxime": "cephalosporins_3g", "ceftazidime": "cephalosporins_3g",
             "ciprofloxacin": "fluoroquinolones", "levofloxacin": "fluoroquinolones",
             "meropenem": "carbapenems", "imipenem": "carbapenems", "ertapenem": "carbapenems"}


def main(paths: list[str]) -> None:
    files = [p for pat in paths for p in glob.glob(pat)]
    if not files:
        sys.exit("no GLASS files given; see module docstring")
    out_rows = []
    for p in files:
        with open(p, newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                cls = CLASS_MAP.get(str(r.get(COLS["antibiotic"], "")).strip().lower())
                if not cls:
                    continue
                pct = r.get(COLS["pct"])
                if pct in (None, "", "NA"):
                    continue
                out_rows.append([ISO3_TO_2.get(r.get(COLS["country"], ""), r.get(COLS["country"], "")), r.get(COLS["pathogen"], "").strip(), cls,
                                 int(float(r.get(COLS["year"]))), float(pct), int(float(r.get(COLS["n"], 0) or 0)),
                                 (r.get(COLS["setting"]) or "hospital").lower()])
    exists = os.path.exists(OUT)
    with open(OUT, "a", newline="") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(["country", "pathogen", "antibiotic_class", "year", "resistant_pct", "n_isolates", "setting"])
        w.writerows(out_rows)
    print(f"appended {len(out_rows)} GLASS rows to {OUT} — REAL data, update seed/README.md")


if __name__ == "__main__":
    main(sys.argv[1:])
