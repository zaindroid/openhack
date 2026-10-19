"""Writes the ILLUSTRATIVE seed CSVs for the Advocate demo (Mar Menor). Deterministic (seeded RNG).
Replace with real extracts via fetch_eea_waterbase.py / fetch_chs_opendata.py; keep the same columns.
Run: python app/data/make_seed_illustrative.py"""
from __future__ import annotations
import csv, os
from datetime import date
import numpy as np

HERE = os.path.dirname(__file__)
SEED = os.path.join(HERE, "seed")
rng = np.random.default_rng(7)


def months(start=(2019, 1), end=(2026, 9)):
    y, m = start
    out = []
    while (y, m) <= end:
        out.append(date(y, m, 1))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def write(name, header, rows):
    with open(os.path.join(SEED, name), "w", newline="") as f:
        w = csv.writer(f); w.writerow(header); w.writerows(rows)


M = months()
n = len(M)
season = np.sin(np.arange(n) * 2 * np.pi / 12)           # seasonal cycle, amplitude 1

# --- inflow nitrate (Rambla del Albujón): seasonal, then a strong rise over the last 14 months -------------------
inflow = 6.0 + 0.8 * season + rng.normal(0, 0.15, n)
inflow[-14:] += np.linspace(0, 5.0, 14)
# --- lagoon centre nitrate follows the inflow with a 2-month lag, damped ---------------------------------------------
lag = 2
lagoon = np.empty(n)
for t in range(n):
    src = inflow[t - lag] if t - lag >= 0 else inflow[0]
    lagoon[t] = 0.6 + 0.12 * src + rng.normal(0, 0.03)
# --- second lagoon station, stable; groundwater stable; chlorophyll and oxygen stable --------------------------------
lagoon2 = 1.1 + 0.08 * season + rng.normal(0, 0.03, n)
gw = 48.0 + 1.5 * season + rng.normal(0, 0.4, n)
chl = 6.0 + 1.2 * season + rng.normal(0, 0.25, n)
do = 7.2 - 0.6 * season + rng.normal(0, 0.1, n)
sal = 43.0 + 0.5 * season + rng.normal(0, 0.1, n)

rows = []
for i, d in enumerate(M):
    ds = d.isoformat()
    rows += [("LG1", ds, "nitrate_mg_l", round(lagoon[i], 3)), ("LG1", ds, "chlorophyll_ug_l", round(chl[i], 2)),
             ("LG1", ds, "dissolved_oxygen_mg_l", round(do[i], 2)), ("LG1", ds, "salinity", round(sal[i], 2)),
             ("LG2", ds, "nitrate_mg_l", round(lagoon2[i], 3)), ("LG2", ds, "chlorophyll_ug_l", round(chl[i] * 0.9, 2)),
             ("IN1", ds, "nitrate_mg_l", round(inflow[i], 2)), ("GW1", ds, "nitrate_mg_l", round(gw[i], 2))]
write("measurements.csv", ["station_id", "date", "parameter", "value"], rows)

write("clients.csv", ["client_id", "name", "statute", "lat", "lon", "guardian_body"],
      [("MM", "Mar Menor", "Ley 19/2022, de 30 de septiembre (BOE) — legal personality of the Mar Menor lagoon and its basin",
        37.70, -0.78, "Comité de Representantes y Comisión de Seguimiento del Mar Menor")])
write("stations.csv", ["station_id", "client_id", "name", "lat", "lon", "kind"],
      [("LG1", "MM", "Mar Menor centre", 37.700, -0.780, "lagoon"), ("LG2", "MM", "Los Urrutias shore", 37.650, -0.850, "lagoon"),
       ("IN1", "MM", "Rambla del Albujón inflow", 37.720, -0.860, "inflow"), ("GW1", "MM", "Campo de Cartagena aquifer well", 37.680, -0.950, "groundwater")])
write("thresholds.csv", ["parameter", "limit_value", "direction", "legal_basis"],
      [("nitrate_mg_l", 1.5, "above", "Ley 3/2020 de recuperación y protección del Mar Menor (Región de Murcia); Ley 19/2022 art. 2 (right to protection)"),
       ("chlorophyll_ug_l", 10.0, "above", "Ley 3/2020 Mar Menor; WFD good ecological status"),
       ("dissolved_oxygen_mg_l", 4.0, "below", "WFD good ecological status (Directive 2000/60/EC)"),
       ("salinity", None, "none", "")])
write("permits.csv", ["permit_id", "holder", "kind", "volume", "unit", "distance_km", "status", "expiry"],
      [("P1", "Agro Campo 7 SL", "fertiliser_plan", 1200, "t_nitrogen_year", 4.0, "renewal_pending", "2026-12-31"),
       ("P2", "Comunidad de Regantes Arco Sur", "abstraction", 850000, "m3_year", 7.0, "active", "2028-06-30"),
       ("P3", "EDAR Los Alcázares", "discharge", 2100000, "m3_year", 3.0, "active", "2029-01-31"),
       ("P4", "Finca Norte", "abstraction", 300000, "m3_year", 21.0, "active", "2027-03-31")])
write("decisions.csv", ["decision_id", "title", "authority", "kind", "distance_km", "submitted", "deadline", "status", "summary"],
      [("D1", "Renewal of fertiliser application plan, Sector 7 Campo de Cartagena", "CARM Consejería de Agua, Agricultura, Ganadería y Pesca",
        "permit_renewal", 3.0, "2026-09-15", "2026-11-20", "open", "Renewal of the fertiliser plan allowing 1,200 t of nitrogen per year on 2,300 ha draining to the Rambla del Albujón, 3 km from the lagoon shore"),
       ("D2", "Residential development plan, Cartagena outskirts", "Ayuntamiento de Cartagena", "planning", 12.0, "2026-08-30", "2026-11-28", "open",
        "Partial urban plan for 340 homes connected to the existing municipal sewer network, outside the lagoon catchment buffer"),
       ("D3", "Logistics park access road", "CARM Fomento", "infrastructure", 18.0, "2026-09-01", "2026-11-30", "open", "New 2 km access road to a logistics park"),
       ("D4", "Desalination brine outfall extension", "CHS", "infrastructure", 2.0, "2025-02-01", "2025-05-01", "closed", "Closed in 2025")])
write("land_use.csv", ["sector", "hectares", "fertiliser_t_year"], [("irrigated horticulture", 41000, 9800), ("rainfed cereals", 12000, 600), ("urban", 7000, 0)])
with open(os.path.join(SEED, "README.md"), "w") as f:
    f.write("# Seed data — ILLUSTRATIVE\n\nThese CSVs are synthetic, generated by `../make_seed_illustrative.py` so the demo and evals run with no network. "
            "Station names and institutions are real places and bodies; every number is invented and shaped so the Skeptic has something to reject.\n\n"
            "Replace with real extracts, same columns: `python app/data/fetch_eea_waterbase.py` (measurements), `python app/data/fetch_chs_opendata.py` (permits/decisions once the API shape is confirmed).\n")
print("seed written:", n, "months")
