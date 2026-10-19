"""Builds app/data/seed/objects.csv and fragmentation_events.csv — ILLUSTRATIVE orbital elements.

Nothing here is a real satellite. The catalogue is constructed so that four conjunctions below 5 km occur inside the
7-day screening window, one per cause the Skeptic can test (fragmentation debris, uncontrolled rocket-body drift,
constellation phasing, natural plane crossing), plus ~55 bystanders that never come close. Real data: fetch_celestrak.py.

Run from the branch root: python3 app/data/make_illustrative_seed.py
"""
from __future__ import annotations
import csv, os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from app.orbit import EPOCH, MU, RE, Elements, propagate, screen  # noqa: E402

rng = np.random.default_rng(7)
SEED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed")


def design_partner(A: Elements, tstar: float, a_B: float, e_B: float, inc_B: float, radial_offset_km: float,
                   prefer_raan: float | None = None) -> Elements:
    """Elements for B at epoch such that at t* B sits radial_offset_km above A's position (in B's own orbit)."""
    r = propagate(A, np.array([tstar]))[0][0]
    rt = r * (1 + radial_offset_km / np.linalg.norm(r))
    x, y, z = rt
    rho, phi, i = np.hypot(x, y), np.arctan2(y, x), np.radians(inc_B)
    s = -z / np.tan(i) / rho
    assert abs(s) <= 1, "inclination too low to contain the target point"
    cands = [phi + np.arcsin(s), phi + np.pi - np.arcsin(s)]
    if prefer_raan is None:
        prefer_raan = np.radians(A.raan)
    raan = min(cands, key=lambda c: abs((c - prefer_raan + np.pi) % (2 * np.pi) - np.pi))
    u = np.arctan2(z / np.sin(i), x * np.cos(raan) + y * np.sin(raan))
    rmag = np.linalg.norm(rt)
    if e_B < 1e-6:
        a_B, nu = rmag, 0.0
    else:
        p = a_B * (1 - e_B ** 2)
        c = (p / rmag - 1) / e_B
        assert abs(c) <= 1, "orbit B does not reach that radius"
        nu = np.arccos(c)
    argp = u - nu
    E = 2 * np.arctan2(np.sqrt(1 - e_B) * np.sin(nu / 2), np.sqrt(1 + e_B) * np.cos(nu / 2))
    M = E - e_B * np.sin(E)
    B = Elements(a_B, e_B, inc_B, np.degrees(raan) % 360, np.degrees(argp) % 360, np.degrees(M) % 360)
    n, d_raan, d_argp, d_m = B.rates()
    B.raan = (B.raan - np.degrees(d_raan * tstar)) % 360
    B.argp = (B.argp - np.degrees(d_argp * tstar)) % 360
    B.m0 = (B.m0 - np.degrees((n + d_m) * tstar)) % 360
    return B


def row(oid, name, typ, owner, country, man, year, parent, mass, el: Elements) -> dict:
    return {"object_id": oid, "name": name, "type": typ, "owner": owner, "country": country, "manoeuvrable": str(man).lower(),
            "launch_year": year, "parent_event": parent or "", "mass_kg": mass, "epoch": EPOCH.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "a_km": round(el.a, 4), "e": round(el.e, 6), "inc_deg": round(el.inc, 4), "raan_deg": round(el.raan, 4),
            "argp_deg": round(el.argp, 4), "m0_deg": round(el.m0, 4), "perigee_km": round(el.a * (1 - el.e) - RE, 1),
            "apogee_km": round(el.a * (1 + el.e) - RE, 1)}


def main() -> None:
    objs: list[dict] = []
    # --- MeshSat constellation shell: 550 km, 53°, 6 planes × 4 ---------------------------------------------------
    a550 = RE + 550.0
    k = 0
    for plane in range(6):
        for s in range(4):
            k += 1
            el = Elements(a550 + rng.uniform(-0.3, 0.3), 0.0002, 53.0, plane * 60.0 + 7.0, 0.0, (s * 90.0 + plane * 15.0) % 360)
            objs.append(row(f"MS-{k:03d}", f"MESHSAT-A-{k:02d}", "payload", "MeshSat Inc", "US", True, 2024, None, 260, el))
    # --- EarthView SSO imaging payloads: 800 km, 98° ------------------------------------------------------------
    a800 = RE + 800.0
    for n in range(1, 9):
        el = Elements(a800 + rng.uniform(-0.5, 0.5), 0.0012, 98.0, 120.0 + 40.0 * ((n - 1) // 2), 90.0, (n * 47.0) % 360)
        objs.append(row(f"EV-{n:02d}", f"EARTHVIEW-{n}", "payload", "EarthView GmbH", "DE", True, 2021 + n % 3, None, 820, el))
    # --- PolarCam: 550 km, 97.6° ----------------------------------------------------------------------------------
    for n in range(1, 7):
        el = Elements(a550 + rng.uniform(-0.5, 0.5), 0.0008, 97.6, 10.0 + 55.0 * n, 45.0, (n * 73.0) % 360)
        objs.append(row(f"PC-{n:02d}", f"POLARCAM-{n}", "payload", "PolarCam SA", "FR", True, 2022, None, 140, el))
    # --- debris cloud from FRAG-2023-A at ~850 km, 99.5° -----------------------------------------------------------
    for n in range(1, 11):
        el = Elements(RE + 850 + rng.uniform(-35, 35), rng.uniform(0.002, 0.02), 99.5 + rng.uniform(-0.6, 0.6), 300.0 + rng.uniform(-4, 4), rng.uniform(0, 360), rng.uniform(0, 360))
        objs.append(row(f"DB-{n:02d}", f"DEB-2023-FRAG-{n:02d}", "debris", "unknown", "", False, 2023, "FRAG-2023-A", 2, el))
    # --- rocket bodies -----------------------------------------------------------------------------------------
    objs.append(row("RB-01", "RB-2017-012C", "rocket_body", "LaunchCo", "RU", False, 2017, None, 1900, Elements((RE + 350 + RE + 1200) / 2, (1200 - 350) / (2 * RE + 1550), 63.4, 200.0, 270.0, 30.0)))
    objs.append(row("RB-02", "RB-2015-003B", "rocket_body", "LaunchCo", "RU", False, 2015, None, 2100, Elements(RE + 980, 0.003, 82.5, 75.0, 10.0, 200.0)))
    # --- MEO nav -------------------------------------------------------------------------------------------------
    for n in range(1, 4):
        objs.append(row(f"NV-{n:02d}", f"NAVSTAR-DEMO-{n}", "payload", "NavCorp", "EU", True, 2019, None, 700, Elements(RE + 20200, 0.0005, 56.0, 60.0 * n, 0.0, 120.0 * n)))

    by_id = {o["object_id"]: o for o in objs}

    def el_of(oid: str) -> Elements:
        o = by_id[oid]
        return Elements(o["a_km"], o["e"], o["inc_deg"], o["raan_deg"], o["argp_deg"], o["m0_deg"])

    # --- designed conjunctions (times in seconds after epoch) ------------------------------------------------------
    # 1. constellation phasing: MESHSAT-A-08 drifts past MESHSAT-A-07 at t = 2.3 d, 0.6 km radial separation
    A = el_of("MS-007")
    B = design_partner(A, 2.3 * 86400, A.a + 0.6, 0.0, 53.0, 0.6)
    by_id["MS-008"].update(row("MS-008", "MESHSAT-A-08", "payload", "MeshSat Inc", "US", True, 2024, None, 260, B))
    # 2. fragmentation debris vs EARTHVIEW-3 at t = 3.6 d, 1.8 km
    A = el_of("EV-03")
    B = design_partner(A, 3.6 * 86400, RE + 850, 0.012, 99.5, 1.8)
    by_id["DB-07"].update(row("DB-07", "DEB-2023-FRAG-07", "debris", "unknown", "", False, 2023, "FRAG-2023-A", 2, B))
    # 3. decaying rocket body (300 × 900 km) co-planar with EARTHVIEW-5 at t = 5.1 d, 3.1 km
    A = el_of("EV-05")
    a_rb = (RE + 300 + RE + 900) / 2
    B = design_partner(A, 5.1 * 86400, a_rb, (900 - 300) / (2 * RE + 1200), 98.0, 3.1)
    objs.append(row("RB-03", "RB-2019-044B", "rocket_body", "LaunchCo", "RU", False, 2019, None, 1700, B))
    by_id["RB-03"] = objs[-1]
    # 4. natural crossing: POLARCAM-2 (97.6°) crosses MESHSAT-A-15 (53°) at t = 1.4 d, 2.4 km
    A = el_of("MS-015")
    B = design_partner(A, 1.4 * 86400, A.a, 0.0, 97.6, 2.4, prefer_raan=np.radians(by_id["PC-02"]["raan_deg"]))
    by_id["PC-02"].update(row("PC-02", "POLARCAM-2", "payload", "PolarCam SA", "FR", True, 2022, None, 140, B))

    conj = screen(objs, days=7.0)
    print(f"{len(objs)} objects, {len(conj)} conjunctions < 5 km:")
    for c in conj:
        print(f"  {by_id[c['a']]['name']} x {by_id[c['b']]['name']}: {c['miss_km']} km at {c['tca']} (alt {c['alt_km']} km)")

    os.makedirs(SEED_DIR, exist_ok=True)
    with open(os.path.join(SEED_DIR, "objects.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(objs[0].keys()))
        w.writeheader(); w.writerows(objs)
    events = [
        {"event_id": "FRAG-2023-A", "parent_object": "EXPLORER-DEMO-9 (illustrative)", "date": "2023-11-14", "pieces": 410, "altitude_km": 850, "cause": "battery rupture"},
        {"event_id": "FRAG-2021-C", "parent_object": "RB-2009-021D (illustrative)", "date": "2021-03-02", "pieces": 120, "altitude_km": 1200, "cause": "residual propellant"},
        {"event_id": "FRAG-2019-B", "parent_object": "TEST-INTERCEPT (illustrative)", "date": "2019-03-27", "pieces": 270, "altitude_km": 280, "cause": "kinetic test"},
        {"event_id": "FRAG-2024-D", "parent_object": "RB-2020-068B (illustrative)", "date": "2024-07-05", "pieces": 90, "altitude_km": 960, "cause": "unknown"},
    ]
    with open(os.path.join(SEED_DIR, "fragmentation_events.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(events[0].keys()))
        w.writeheader(); w.writerows(events)
    print("written", SEED_DIR)


if __name__ == "__main__":
    main()
