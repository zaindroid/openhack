"""Writes the ILLUSTRATIVE seed CSVs under app/data/seed/. Deterministic; no randomness beyond a fixed seed.
The region is the Pittsburgh area (Allegheny / Washington / Westmoreland counties, PA) because it is the classic
bridge county, but every name, rating and date here is invented. Real data: run fetch_nbi.py / fetch_nid.py / fetch_fema_floods.py.
"""
from __future__ import annotations
import csv, os, random

HERE = os.path.dirname(__file__)
SEED = os.path.join(HERE, "seed")
random.seed(42)

counties = {"Allegheny": (40.44, -79.99), "Washington": (40.17, -80.25), "Westmoreland": (40.31, -79.54)}
materials = ["steel", "prestressed concrete", "concrete", "steel truss"]

bridges = []
# --- the three teaching cases -------------------------------------------------------------------------------------
bridges.append(dict(structure_id="PA-AL-0001", name="Mon Valley Crossing", state="PA", county="Allegheny", lat=40.428, lon=-79.973,
                    year_built=1962, year_reconstructed="", design_life_years=50, deck_rating=4, superstructure_rating=5, substructure_rating=3,
                    scour_critical="false", adt=18400, adt_year=2019, last_inspection="2022-01-14", inspection_interval_months=24,
                    material="steel truss", posted_load_limit="false", replacement_cost_usd=42000000))
bridges.append(dict(structure_id="PA-WA-0002", name="Chartiers Creek Span", state="PA", county="Washington", lat=40.205, lon=-80.212,
                    year_built=1998, year_reconstructed="", design_life_years=75, deck_rating=4, superstructure_rating=6, substructure_rating=5,
                    scour_critical="true", adt=9600, adt_year=2021, last_inspection="2026-03-02", inspection_interval_months=24,
                    material="prestressed concrete", posted_load_limit="false", replacement_cost_usd=11000000))
bridges.append(dict(structure_id="PA-AL-0003", name="Turtle Creek Viaduct", state="PA", county="Allegheny", lat=40.412, lon=-79.826,
                    year_built=1971, year_reconstructed="1994", design_life_years=50, deck_rating=5, superstructure_rating=4, substructure_rating=5,
                    scour_critical="false", adt=24100, adt_year=2015, last_inspection="2025-11-20", inspection_interval_months=24,
                    material="steel", posted_load_limit="false", replacement_cost_usd=58000000))
# --- healthy majority ----------------------------------------------------------------------------------------------
names = ["Ridge", "Hollow", "Run", "Creek", "Mill", "Ferry", "Station", "Church", "Orchard", "Quarry", "Forge", "Landing", "Grove",
         "Summit", "Meadow", "Junction", "Bend", "Falls", "Terrace", "Point", "Harbor", "Narrows", "Heights", "Gap", "Crossing",
         "Fork", "Valley", "Island", "Park", "Trestle", "Overpass", "Bypass", "Parkway", "Boulevard", "Avenue", "Road", "Lane"]
for i, nm in enumerate(names[:37], start=4):
    county = random.choice(list(counties))
    base = counties[county]
    yb = random.randint(1975, 2016)
    bridges.append(dict(structure_id=f"PA-{county[:2].upper()}-{i:04d}", name=f"{random.choice(['North','South','East','West','Old','New'])} {nm} Bridge",
                        state="PA", county=county, lat=round(base[0] + random.uniform(-0.12, 0.12), 3), lon=round(base[1] + random.uniform(-0.15, 0.15), 3),
                        year_built=yb, year_reconstructed="", design_life_years=random.choice([75, 75, 100]),
                        deck_rating=random.randint(6, 8), superstructure_rating=random.randint(6, 8), substructure_rating=random.randint(6, 8),
                        scour_critical=random.choice(["false", "false", "false", "true"]), adt=random.randint(800, 22000), adt_year=random.randint(2019, 2024),
                        last_inspection=f"{random.randint(2025, 2026)}-{random.randint(1, 9):02d}-{random.randint(1, 28):02d}",
                        inspection_interval_months=24, material=random.choice(materials), posted_load_limit="false",
                        replacement_cost_usd=random.randint(3, 30) * 1_000_000))

dams = [
    dict(dam_id="PA-D-0001", name="Loyalhanna Ridge Dam", lat=40.305, lon=-79.395, year_completed=1958, hazard_class="high", condition="poor",
         last_inspection="2025-06-10", population_downstream=4200, eap_present="false", replacement_cost_usd=35000000),
    dict(dam_id="PA-D-0002", name="Beaver Run Reservoir Dam", lat=40.395, lon=-79.620, year_completed=1951, hazard_class="high", condition="poor",
         last_inspection="2026-02-18", population_downstream=2600, eap_present="true", replacement_cost_usd=28000000),
    dict(dam_id="PA-D-0003", name="Peters Lake Dam", lat=40.270, lon=-80.090, year_completed=1991, hazard_class="significant", condition="satisfactory",
         last_inspection="2026-04-01", population_downstream=900, eap_present="true", replacement_cost_usd=9000000),
    dict(dam_id="PA-D-0004", name="North Park Lake Dam", lat=40.600, lon=-80.010, year_completed=2003, hazard_class="high", condition="satisfactory",
         last_inspection="2025-10-05", population_downstream=6100, eap_present="true", replacement_cost_usd=21000000),
    dict(dam_id="PA-D-0005", name="Mingo Creek Dam", lat=40.215, lon=-80.030, year_completed=1988, hazard_class="low", condition="fair",
         last_inspection="2025-08-22", population_downstream=40, eap_present="false", replacement_cost_usd=4000000),
    dict(dam_id="PA-D-0006", name="Yough Headwater Dam", lat=40.230, lon=-79.590, year_completed=1996, hazard_class="significant", condition="fair",
         last_inspection="2026-01-12", population_downstream=700, eap_present="true", replacement_cost_usd=12000000),
    dict(dam_id="PA-D-0007", name="Deer Lakes Dam", lat=40.620, lon=-79.800, year_completed=2010, hazard_class="low", condition="satisfactory",
         last_inspection="2026-05-30", population_downstream=15, eap_present="true", replacement_cost_usd=3000000),
    dict(dam_id="PA-D-0008", name="Raccoon Creek Dam", lat=40.500, lon=-80.420, year_completed=1979, hazard_class="significant", condition="satisfactory",
         last_inspection="2025-12-15", population_downstream=1100, eap_present="true", replacement_cost_usd=8000000),
]

floods = []
for county, counts in {"Allegheny": {2021: 1, 2022: 0, 2023: 1, 2024: 0, 2025: 0, 2026: 0},
                       "Washington": {2021: 0, 2022: 1, 2023: 1, 2024: 2, 2025: 1, 2026: 0},
                       "Westmoreland": {2021: 1, 2022: 0, 2023: 0, 2024: 1, 2025: 0, 2026: 0}}.items():
    for y, n in counts.items():
        floods.append(dict(county=county, year=y, events=n))

traffic = []
growth = {"Allegheny": 2.6, "Washington": 1.2, "Westmoreland": 1.0}   # % per year, base 100 in 2015
for county, g in growth.items():
    for y in range(2015, 2027):
        traffic.append(dict(county=county, year=y, adt_index=round(100 * (1 + g / 100) ** (y - 2015), 1)))


def write(name: str, rows: list[dict]) -> None:
    os.makedirs(SEED, exist_ok=True)
    with open(os.path.join(SEED, name), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)


if __name__ == "__main__":
    write("bridges.csv", bridges); write("dams.csv", dams); write("floods.csv", floods); write("traffic_growth.csv", traffic)
    print(f"wrote {len(bridges)} bridges, {len(dams)} dams, {len(floods)} flood rows, {len(traffic)} traffic rows to {SEED}")
