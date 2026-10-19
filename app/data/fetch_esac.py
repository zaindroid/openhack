"""ECDC ESAC-Net (antimicrobial consumption) → app/data/seed/consumption.csv

Source: https://www.ecdc.europa.eu/en/antimicrobial-consumption/surveillance-and-disease-data/database
The interactive database exports CSV per ATC group and sector (community / hospital) in DDD per 1 000 inhabitants per day.
Flow: export "Trend of consumption" for ATC groups J01DD (3rd-gen cephalosporins), J01MA (fluoroquinolones), J01DH
(carbapenems), all countries, all years, both sectors → app/data/raw/esac/*.csv → run this script.
Sectors are summed to one 'human' row per country/class/year (the domain compares human use with resistance).
"""
from __future__ import annotations
import csv, glob, os, sys
from collections import defaultdict

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed", "consumption.csv")
ATC = {"J01DD": "cephalosporins_3g", "J01MA": "fluoroquinolones", "J01DH": "carbapenems"}
ISO2 = {"Germany": "DE", "France": "FR", "Italy": "IT", "Spain": "ES", "Netherlands": "NL", "Poland": "PL", "Austria": "AT", "Belgium": "BE",
        "Sweden": "SE", "Denmark": "DK", "Finland": "FI", "Portugal": "PT", "Greece": "EL", "Ireland": "IE", "Czechia": "CZ", "Hungary": "HU"}


def main(paths: list[str]) -> None:
    files = [p for pat in paths for p in glob.glob(pat)]
    if not files:
        sys.exit("no ESAC-Net export CSVs given; see module docstring")
    acc: dict[tuple, float] = defaultdict(float)
    for p in files:
        with open(p, newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                code = next((k for k in ATC if k in (r.get("ATC group") or r.get("ATC") or "")), None)
                val = (r.get("DDD per 1000 inhabitants per day") or r.get("Value") or "").replace(",", ".").strip()
                if not code or not val:
                    continue
                country = ISO2.get(r.get("Country", "").strip(), r.get("Country", "").strip())
                acc[(country, int(float(r.get("Year"))), ATC[code])] += float(val)
    with open(OUT, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["country", "year", "antibiotic_class", "ddd_per_1000_per_day", "sector"])
        for (c, y, k), v in sorted(acc.items()):
            w.writerow([c, y, k, round(v, 3), "human"])
    print(f"wrote {OUT}: {len(acc)} rows — REAL data, update seed/README.md")


if __name__ == "__main__":
    main(sys.argv[1:])
