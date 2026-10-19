"""Builds the ILLUSTRATIVE seed corpus for Lazarus into app/data/seed/*.csv.

Nothing here is a real publication. Titles, abstracts and entity lists are invented to exercise the three Skeptic
conditions (method overlap, no citation path, time gap). Replace with fetch_openalex.py output for real runs.
Run: python app/data/build_seed.py
"""
from __future__ import annotations
import csv, os

OUT = os.path.join(os.path.dirname(__file__), "seed")

FIELDS = [
    ("robotics", "engineering"), ("control_engineering", "engineering"), ("tribology", "engineering"),
    ("computer_vision", "computing"), ("machine_learning", "computing"),
    ("geophysics", "earth_science"), ("seismology", "earth_science"),
    ("ecology", "life_science"), ("evolutionary_biology", "life_science"),
    ("epidemiology", "health_science"), ("public_health", "health_science"),
    ("materials_science", "physical_science"), ("polymer_physics", "physical_science"),
]

# entity -> kind (method | mechanism | object | generic)
ENTITY_KINDS = {
    "stick-slip": "mechanism", "friction instability": "mechanism", "precursor signal": "method",
    "acoustic emission": "method", "fault gouge": "object", "tactile sensing": "method", "grasp": "object",
    "slip onset": "mechanism", "rate-and-state friction": "method", "creep": "mechanism", "polymer film": "object",
    "metapopulation": "mechanism", "patch dynamics": "mechanism", "rescue effect": "mechanism",
    "extinction-recolonisation": "mechanism", "habitat fragmentation": "object", "vaccination coverage": "object",
    "incidence": "object", "spatial model": "method", "butterfly": "object", "measles": "object",
    "crack arrest": "mechanism", "fracture toughness": "method", "confining pressure": "object",
    "brittle fracture": "mechanism", "ceramic composite": "object", "self-healing": "mechanism",
    "microcapsule": "object", "rock": "object", "domain shift": "mechanism", "segmentation": "object",
    "robust estimation": "method", "model uncertainty": "mechanism", "h-infinity": "method",
    "dynamics": "generic", "model": "generic", "data": "generic", "analysis": "generic", "system": "generic",
    "optimisation": "generic", "simulation": "generic", "network": "generic", "noise": "generic",
    "image": "object", "convolution": "method", "attention": "method", "transfer learning": "method",
    "population": "generic", "dispersal": "mechanism", "epidemic threshold": "method", "contact network": "object",
    "wear": "mechanism", "lubrication": "object", "surface roughness": "object", "sensor fusion": "method",
    "kalman filter": "method", "manipulator": "object", "fatigue": "mechanism", "microstructure": "object",
    "earthquake": "object", "laboratory fault": "object", "glass transition": "mechanism",
}

# paper_id, title, field, year, cited_by_count, entities, abstract
PAPERS = [
    # --- seismology / geophysics ---
    ("S1994", "Stick-slip precursors in laboratory faults: acoustic emission before slip onset", "seismology", 1994, 210,
     ["stick-slip", "friction instability", "precursor signal", "acoustic emission", "fault gouge", "laboratory fault", "slip onset"],
     "Laboratory faults loaded to failure show a reproducible rise in acoustic emission seconds before slip onset; the precursor signal scales with the friction instability."),
    ("S1998", "Rate-and-state friction and the nucleation of unstable slip", "seismology", 1998, 340,
     ["rate-and-state friction", "stick-slip", "slip onset", "laboratory fault", "model"],
     "A rate-and-state friction law reproduces stick-slip cycles observed on laboratory faults."),
    ("G1979", "Crack arrest in brittle rock under confining pressure", "geophysics", 1979, 95,
     ["crack arrest", "fracture toughness", "confining pressure", "brittle fracture", "rock"],
     "Measured fracture toughness of brittle rock rises with confining pressure, producing crack arrest at depth."),
    ("G2010", "Friction instability of fault gouge at seismic slip rates", "geophysics", 2010, 120,
     ["friction instability", "fault gouge", "stick-slip", "earthquake", "data"],
     "High-velocity friction experiments on fault gouge show a friction instability that controls stick-slip at seismic slip rates."),
    ("G2015", "Creep transients before earthquakes: a precursor signal in strain data", "geophysics", 2015, 60,
     ["creep", "precursor signal", "earthquake", "data", "analysis"],
     "Strain data show creep transients that act as a precursor signal before some earthquakes."),
    ("G1988", "Seismic noise analysis for site characterisation", "geophysics", 1988, 40,
     ["noise", "analysis", "data", "earthquake"], "Ambient seismic noise is analysed to characterise sites."),
    # --- ecology / evolutionary biology ---
    ("E1985", "Metapopulation persistence of butterflies in fragmented habitat", "ecology", 1985, 410,
     ["metapopulation", "patch dynamics", "rescue effect", "extinction-recolonisation", "habitat fragmentation", "butterfly", "dispersal"],
     "A metapopulation of butterflies persists through extinction-recolonisation among patches; the rescue effect raises patch occupancy where dispersal links patches."),
    ("E1991", "Patch dynamics and the rescue effect in island populations", "ecology", 1991, 150,
     ["patch dynamics", "rescue effect", "dispersal", "population", "model"],
     "Island populations show patch dynamics in which immigration rescues small patches from extinction."),
    ("E2019", "Spatial models of extinction-recolonisation under climate shifts", "ecology", 2019, 55,
     ["spatial model", "extinction-recolonisation", "metapopulation", "dispersal", "simulation"],
     "Spatial models show how extinction-recolonisation balances change under shifting climate."),
    ("E2003", "Self-organisation of vegetation patterns in arid systems", "ecology", 2003, 300,
     ["self-healing", "dynamics", "model", "system", "simulation"],
     "Vegetation patterns self-organise; damaged patches recover (self-healing) through local feedbacks."),
    ("V1996", "Dispersal and the genetics of fragmented populations", "evolutionary_biology", 1996, 80,
     ["dispersal", "habitat fragmentation", "population", "data"], "Genetic data reveal dispersal across fragmented habitat."),
    # --- epidemiology / public health ---
    ("H2021", "Metapopulation models for vaccine-preventable disease in connected cities", "epidemiology", 2021, 30,
     ["metapopulation", "spatial model", "vaccination coverage", "incidence", "measles"],
     "Metapopulation spatial models link vaccination coverage to measles incidence across connected cities."),
    ("H2016", "Epidemic thresholds on contact networks", "epidemiology", 2016, 200,
     ["epidemic threshold", "contact network", "network", "model"], "Epidemic thresholds depend on contact network structure."),
    ("H2009", "Measles incidence and vaccination coverage in Europe", "public_health", 2009, 90,
     ["measles", "vaccination coverage", "incidence", "data"], "Surveillance data relate measles incidence to coverage."),
    ("H2023", "Noise in surveillance data and outbreak detection", "epidemiology", 2023, 12,
     ["noise", "data", "analysis", "incidence"], "Surveillance noise limits outbreak detection."),
    # --- robotics / control / tribology ---
    ("R2020", "Tactile sensing for grasp stability in soft manipulators", "robotics", 2020, 70,
     ["tactile sensing", "grasp", "manipulator", "sensor fusion", "data"], "Tactile arrays estimate grasp stability on a soft manipulator."),
    ("R2022", "Learning slip onset from fingertip vibration", "robotics", 2022, 45,
     ["slip onset", "tactile sensing", "grasp", "transfer learning", "data"], "A learned detector flags slip onset from fingertip vibration."),
    ("R2018", "Friction instability in robot joints: a tribological view", "robotics", 2018, 25,
     ["friction instability", "wear", "manipulator", "model"], "Joint friction instability is modelled from wear measurements."),
    ("C2005", "Robust estimation under model uncertainty", "control_engineering", 2005, 500,
     ["robust estimation", "model uncertainty", "h-infinity", "kalman filter", "system"],
     "H-infinity and Kalman-type estimators are compared under model uncertainty."),
    ("C1990", "Kalman filtering with uncertain dynamics", "control_engineering", 1990, 220,
     ["kalman filter", "model uncertainty", "dynamics", "system"], "Kalman filters under uncertain dynamics."),
    ("T2001", "Stick-slip in lubricated sliding contacts", "tribology", 2001, 130,
     ["stick-slip", "lubrication", "surface roughness", "friction instability", "wear"],
     "Lubricated contacts show stick-slip governed by surface roughness."),
    # --- computer vision / machine learning ---
    ("V2020", "Robust segmentation with uncertainty-aware estimation", "computer_vision", 2020, 160,
     ["segmentation", "robust estimation", "model uncertainty", "convolution", "image"],
     "Segmentation networks with uncertainty-aware robust estimation."),
    ("V2017", "Attention for dense prediction", "computer_vision", 2017, 900,
     ["attention", "segmentation", "image", "convolution"], "Attention improves dense prediction."),
    ("M2019", "Transfer learning under domain shift", "machine_learning", 2019, 700,
     ["transfer learning", "domain shift", "model", "data"], "Transfer learning mitigates domain shift."),
    ("M2012", "Optimisation methods for deep networks", "machine_learning", 2012, 1500,
     ["optimisation", "network", "model", "data"], "Optimisation for deep networks."),
    ("V2023", "Segmentation under domain shift with noise-robust training", "computer_vision", 2023, 40,
     ["segmentation", "domain shift", "noise", "image", "model"], "Noise-robust training for segmentation under domain shift."),
    # --- materials / polymer physics ---
    ("P2023", "Friction instability in thin polymer films", "polymer_physics", 2023, 8,
     ["friction instability", "polymer film", "stick-slip", "glass transition", "data"],
     "Thin polymer films show stick-slip friction instability near the glass transition."),
    ("MS2015", "Self-healing polymers with embedded microcapsules", "materials_science", 2015, 420,
     ["self-healing", "microcapsule", "fatigue", "microstructure"], "Microcapsules release healing agent at cracks."),
    ("MS2008", "Fracture toughness of ceramic composites", "materials_science", 2008, 260,
     ["fracture toughness", "ceramic composite", "brittle fracture", "microstructure"], "Toughness of ceramic composites."),
    ("MS1998", "Fatigue crack growth in metals: an analysis", "materials_science", 1998, 180,
     ["fatigue", "analysis", "data", "model"], "Fatigue crack growth analysed."),
    ("P2006", "Glass transition and creep in amorphous polymers", "polymer_physics", 2006, 75,
     ["glass transition", "creep", "polymer film", "dynamics"], "Creep near the glass transition."),
    # --- filler papers so fields have depth ---
    ("S2005", "Earthquake catalogue analysis", "seismology", 2005, 50, ["earthquake", "data", "analysis"], "Catalogue analysis."),
    ("S1980", "Laboratory fault mechanics", "seismology", 1980, 140, ["laboratory fault", "rock", "stick-slip"], "Early laboratory fault work."),
    ("E2012", "Dispersal networks of pollinators", "ecology", 2012, 60, ["dispersal", "network", "data"], "Pollinator dispersal networks."),
    ("E1978", "Population dynamics of island birds", "ecology", 1978, 90, ["population", "dynamics", "dispersal"], "Island bird dynamics."),
    ("H2018", "Spatial model of dengue incidence", "epidemiology", 2018, 70, ["spatial model", "incidence", "data"], "Dengue spatial model."),
    ("R2015", "Sensor fusion for mobile manipulators", "robotics", 2015, 110, ["sensor fusion", "manipulator", "kalman filter"], "Fusion for manipulators."),
    ("R2024", "Contact-rich assembly with learned policies", "robotics", 2024, 15, ["manipulator", "grasp", "transfer learning", "simulation"], "Learned assembly policies."),
    ("C2012", "Model uncertainty in networked control", "control_engineering", 2012, 90, ["model uncertainty", "network", "system"], "Networked control."),
    ("V2015", "Convolutional segmentation", "computer_vision", 2015, 2000, ["segmentation", "convolution", "image"], "Fully convolutional segmentation."),
    ("M2021", "Attention under domain shift", "machine_learning", 2021, 120, ["attention", "domain shift", "model"], "Attention and shift."),
    ("MS2020", "Microstructure and fatigue of additively manufactured alloys", "materials_science", 2020, 95, ["microstructure", "fatigue", "data"], "AM alloy fatigue."),
    ("G1995", "Confining pressure and rock creep", "geophysics", 1995, 45, ["confining pressure", "creep", "rock"], "Rock creep under pressure."),
    ("T2014", "Wear mapping of lubricated steels", "tribology", 2014, 35, ["wear", "lubrication", "surface roughness"], "Wear maps."),
    ("P2018", "Polymer film adhesion", "polymer_physics", 2018, 30, ["polymer film", "surface roughness", "data"], "Adhesion of films."),
]

# problem_id, title, field, year, statement, entities
PROBLEMS = [
    ("PR1", "Slip detection in contact-rich manipulation before the object moves", "robotics", 2025,
     "Grippers detect slip only after the object has moved. We need a precursor signal of slip onset from tactile sensing, "
     "ideally from the friction instability itself rather than from learned appearance.",
     ["stick-slip", "friction instability", "precursor signal", "tactile sensing", "grasp", "slip onset", "data"]),
    ("PR2", "Predicting measles re-emergence in patchy vaccination landscapes", "epidemiology", 2024,
     "Incidence returns in regions where coverage is high on average but patchy. We lack a theory of how well-covered patches "
     "rescue poorly covered ones and when extinction-recolonisation of the virus tips to persistence.",
     ["metapopulation", "patch dynamics", "rescue effect", "extinction-recolonisation", "vaccination coverage", "incidence", "measles", "model"]),
    ("PR3", "Robust segmentation under domain shift without labelled target data", "computer_vision", 2025,
     "Segmentation degrades under domain shift; we want estimation that is robust to model uncertainty without target labels.",
     ["segmentation", "domain shift", "robust estimation", "model uncertainty", "image", "model", "data"]),
    ("PR4", "Crack arrest in self-healing ceramic composites", "materials_science", 2024,
     "Self-healing fills cracks but does not stop them growing first. We want a mechanism of crack arrest that raises "
     "effective fracture toughness before healing acts.",
     ["crack arrest", "fracture toughness", "self-healing", "ceramic composite", "brittle fracture", "microcapsule", "model"]),
]

# citing -> cited. These encode the "already connected" rejections.
CITATIONS = [
    ("R2018", "G2010"),   # robotics already cites G2010 → G2010 is not a rediscovery for PR1 (1 hop)
    ("R2022", "R2018"), ("R2020", "R2015"), ("R2024", "R2022"),
    ("H2021", "E2019"),   # epidemiology already cites E2019 → not a rediscovery for PR2 (1 hop)
    ("H2021", "H2016"), ("H2023", "H2021"), ("H2018", "H2016"),
    ("V2020", "C2005"),   # computer vision already cites C2005 (1 hop) → PR3 candidate rejected
    ("V2023", "M2019"), ("M2019", "M2012"), ("V2023", "V2020"), ("M2021", "V2017"),
    ("V2015", "M2012"), ("C2012", "C2005"), ("C2005", "C1990"),
    ("MS2015", "MS2008"), ("MS2020", "MS1998"), ("MS2008", "MS1998"),
    ("S1998", "S1994"), ("S1994", "S1980"), ("G2010", "S1998"), ("G2015", "G1995"),
    ("E1991", "E1985"), ("E2019", "E1991"), ("E2012", "E2003"), ("V1996", "E1985"),
    ("T2001", "S1998"), ("T2014", "T2001"), ("P2023", "P2006"), ("P2018", "P2006"),
]


def write(name: str, header: list[str], rows: list[list]) -> None:
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name), "w", newline="") as f:
        w = csv.writer(f); w.writerow(header); w.writerows(rows)


def main() -> None:
    write("fields.csv", ["field", "parent_field"], [list(x) for x in FIELDS])
    write("papers.csv", ["paper_id", "title", "field", "year", "cited_by_count", "entities", "abstract"],
          [[p[0], p[1], p[2], p[3], p[4], ";".join(p[5]), p[6]] for p in PAPERS])
    write("paper_entities.csv", ["paper_id", "entity"], [[p[0], e] for p in PAPERS for e in p[5]])
    write("problems.csv", ["problem_id", "title", "field", "year", "statement", "key_entities"],
          [[p[0], p[1], p[2], p[3], p[4], ";".join(p[5])] for p in PROBLEMS])
    write("problem_entities.csv", ["problem_id", "entity"], [[p[0], e] for p in PROBLEMS for e in p[5]])
    write("citations.csv", ["citing_id", "cited_id"], [list(c) for c in CITATIONS])
    used = {e for p in PAPERS for e in p[5]} | {e for p in PROBLEMS for e in p[5]}
    missing = sorted(used - set(ENTITY_KINDS))
    if missing:
        raise SystemExit(f"entities without a kind: {missing}")
    write("entity_kinds.csv", ["entity", "kind"], [[e, k] for e, k in sorted(ENTITY_KINDS.items())])
    print(f"seed written to {OUT}: {len(PAPERS)} papers, {len(PROBLEMS)} problems, {len(CITATIONS)} citations, {len(ENTITY_KINDS)} entities")


if __name__ == "__main__":
    main()
