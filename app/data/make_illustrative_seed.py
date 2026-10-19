"""Writes the ILLUSTRATIVE seed CSVs under app/data/seed/. Numbers are invented to exercise every verdict path;
they are not WHO GLASS or ECDC figures. Replace them with real exports via fetch_ecdc_atlas.py / fetch_glass.py.

python3 app/data/make_illustrative_seed.py
"""
from __future__ import annotations
import csv, os

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = os.path.join(HERE, "seed")
YEARS = list(range(2019, 2025))
COUNTRIES = ["DE", "FR", "IT", "ES", "NL", "PL"]
PATHOGENS = {"Escherichia coli": ("community", False), "Klebsiella pneumoniae": ("hospital", False),
             "Salmonella spp.": ("community", True), "Staphylococcus aureus": ("hospital", False)}
CLASSES = ["cephalosporins_3g", "fluoroquinolones", "carbapenems"]


def lin(a: float, b: float, n: int = len(YEARS)) -> list[float]:
    return [round(a + (b - a) * i / (n - 1), 1) for i in range(n)]


def main() -> None:
    os.makedirs(SEED, exist_ok=True)
    # ---- resistance: flat baseline everywhere, then the story pairs -------------------------------------------
    base = {"cephalosporins_3g": 10.0, "fluoroquinolones": 14.0, "carbapenems": 3.0}
    res: dict[tuple, list[float]] = {}
    niso: dict[tuple, list[int]] = {}
    for c in COUNTRIES:
        for p in PATHOGENS:
            for k in CLASSES:
                res[(c, p, k)] = lin(base[k], base[k] + 1.2)           # ≤ 1.2 pt drift → no signal
                niso[(c, p, k)] = [900 + 40 * i for i in range(len(YEARS))]
    # 1. DE · E. coli vs 3rd-gen cephalosporins: human prescribing (consumption rose 2020–2022)
    res[("DE", "Escherichia coli", "cephalosporins_3g")] = [11.0, 11.5, 12.0, 15.0, 18.5, 21.0]
    niso[("DE", "Escherichia coli", "cephalosporins_3g")] = [2100, 2150, 2200, 2260, 2300, 2340]
    # 2. PL · Salmonella vs fluoroquinolones: livestock use (mg/PCU rose), human consumption flat
    res[("PL", "Salmonella spp.", "fluoroquinolones")] = [7.5, 7.8, 8.0, 11.0, 14.0, 17.0]
    niso[("PL", "Salmonella spp.", "fluoroquinolones")] = [640, 660, 680, 700, 720, 750]
    # 3. IT · K. pneumoniae vs carbapenems: surveillance artifact (new labs 2022, isolates more than doubled)
    res[("IT", "Klebsiella pneumoniae", "carbapenems")] = [19.0, 19.5, 20.0, 27.0, 29.5, 31.0]
    niso[("IT", "Klebsiella pneumoniae", "carbapenems")] = [580, 590, 600, 1300, 1380, 1420]
    # 4. FR · K. pneumoniae vs 3rd-gen cephalosporins: unexplained (nothing moves)
    res[("FR", "Klebsiella pneumoniae", "cephalosporins_3g")] = [14.0, 14.5, 15.0, 17.5, 20.0, 22.0]
    niso[("FR", "Klebsiella pneumoniae", "cephalosporins_3g")] = [1500, 1520, 1550, 1580, 1600, 1640]
    # 5. ES · E. coli vs carbapenems: importation (imported share 22 → 38 %)
    res[("ES", "Escherichia coli", "carbapenems")] = [2.0, 2.2, 2.5, 4.5, 6.5, 8.0]
    niso[("ES", "Escherichia coli", "carbapenems")] = [1900, 1950, 2000, 2050, 2100, 2150]
    with open(os.path.join(SEED, "resistance.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["country", "pathogen", "antibiotic_class", "year", "resistant_pct", "n_isolates", "setting"])
        for (c, p, k), vals in res.items():
            for i, y in enumerate(YEARS):
                w.writerow([c, p, k, y, vals[i], niso[(c, p, k)][i], PATHOGENS[p][0]])

    # ---- human consumption (DDD / 1000 inhabitants / day) ---------------------------------------------------------
    cons_base = {"cephalosporins_3g": 1.8, "fluoroquinolones": 1.4, "carbapenems": 0.06}
    with open(os.path.join(SEED, "consumption.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["country", "year", "antibiotic_class", "ddd_per_1000_per_day", "sector"])
        for c in COUNTRIES:
            for k in CLASSES:
                vals = lin(cons_base[k], cons_base[k] * 1.02)
                if (c, k) == ("DE", "cephalosporins_3g"):
                    vals = [1.8, 1.85, 2.15, 2.45, 2.5, 2.52]          # +~30 % 2020→2022, one–two years ahead of the rise
                for i, y in enumerate(YEARS):
                    w.writerow([c, y, k, round(vals[i], 3), "human"])

    # ---- livestock sales (mg per population correction unit) ------------------------------------------------------
    liv_base = {"cephalosporins_3g": 0.3, "fluoroquinolones": 2.5, "carbapenems": 0.0}
    with open(os.path.join(SEED, "livestock_use.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["country", "year", "antibiotic_class", "mg_per_pcu"])
        for c in COUNTRIES:
            for k in CLASSES:
                vals = lin(liv_base[k], liv_base[k] * 0.98)
                if (c, k) == ("PL", "fluoroquinolones"):
                    vals = [2.5, 2.6, 2.7, 3.3, 3.6, 3.8]               # +~40 % over the window
                for i, y in enumerate(YEARS):
                    w.writerow([c, y, k, round(vals[i], 3)])

    # ---- surveillance changes ----------------------------------------------------------------------------------
    with open(os.path.join(SEED, "surveillance_changes.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["country", "year", "change", "note"])
        for c in COUNTRIES:
            for y in YEARS:
                if (c, y) == ("IT", 2022):
                    w.writerow([c, y, "new_labs_added", "14 regional laboratories joined the network; tertiary hospitals over-represented"])
                elif (c, y) == ("NL", 2020):
                    w.writerow([c, y, "coverage_expanded", "two provinces added; isolate counts changed < 10 %"])
                else:
                    w.writerow([c, y, "none", ""])

    # ---- travel / importation --------------------------------------------------------------------------------
    with open(os.path.join(SEED, "travel_import.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["country", "year", "pathogen", "imported_share_pct"])
        for c in COUNTRIES:
            for p in PATHOGENS:
                vals = lin(10.0, 11.0)
                if (c, p) == ("ES", "Escherichia coli"):
                    vals = [20.0, 21.0, 22.0, 28.0, 34.0, 38.0]
                for i, y in enumerate(YEARS):
                    w.writerow([c, y, p, vals[i]])

    # ---- pathogens ---------------------------------------------------------------------------------------------
    with open(os.path.join(SEED, "pathogens.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["pathogen", "zoonotic", "note"])
        w.writerow(["Escherichia coli", "false", "mostly human-to-human in surveillance series; food-chain ESBL contribution is debated and not assumed here"])
        w.writerow(["Klebsiella pneumoniae", "false", "healthcare-associated"])
        w.writerow(["Salmonella spp.", "true", "food-chain pathogen; poultry and pig reservoirs"])
        w.writerow(["Staphylococcus aureus", "false", "livestock-associated clones exist but are a minority in these series"])
    print("illustrative seed written to", SEED)


if __name__ == "__main__":
    main()
