"""Two-body Keplerian propagation with J2 secular rates, and a conjunction screener. numpy only.

This is SCREENING, not operations: no drag, no SGP4, no covariance. Real runs feed TLEs through the `sgp4` package
(see app/data/fetch_celestrak.py); the screener below accepts any (a, e, i, RAAN, argp, M0) set at a common epoch.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import numpy as np

MU = 398600.4418          # km^3/s^2
RE = 6378.137             # km
J2 = 1.08262668e-3
EPOCH = datetime(2026, 10, 20, 0, 0, 0, tzinfo=timezone.utc)


@dataclass
class Elements:
    a: float          # km
    e: float
    inc: float        # deg
    raan: float       # deg
    argp: float       # deg
    m0: float         # deg at epoch

    def rates(self) -> tuple[float, float, float, float]:
        """mean motion n plus J2 secular rates (rad/s): n, dRAAN, dargp, dM."""
        n = np.sqrt(MU / self.a ** 3)
        i = np.radians(self.inc)
        p = self.a * (1 - self.e ** 2)
        k = 1.5 * J2 * (RE / p) ** 2 * n
        d_raan = -k * np.cos(i)
        d_argp = k * (2 - 2.5 * np.sin(i) ** 2)
        d_m = k * np.sqrt(1 - self.e ** 2) * (1 - 1.5 * np.sin(i) ** 2)
        return n, d_raan, d_argp, d_m


def kepler_E(M: np.ndarray, e: float) -> np.ndarray:
    E = M.copy() if e < 0.8 else np.full_like(M, np.pi)
    for _ in range(12):
        E = E - (E - e * np.sin(E) - M) / (1 - e * np.cos(E))
    return E


def propagate(el: Elements, t: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Positions (T,3) and velocities (T,3) in ECI km, km/s at seconds-since-epoch t."""
    n, d_raan, d_argp, d_m = el.rates()
    M = np.radians(el.m0) + (n + d_m) * t
    raan = np.radians(el.raan) + d_raan * t
    argp = np.radians(el.argp) + d_argp * t
    i = np.radians(el.inc)
    E = kepler_E(np.mod(M, 2 * np.pi), el.e)
    nu = 2 * np.arctan2(np.sqrt(1 + el.e) * np.sin(E / 2), np.sqrt(1 - el.e) * np.cos(E / 2))
    p = el.a * (1 - el.e ** 2)
    r = p / (1 + el.e * np.cos(nu))
    # perifocal
    x_p, y_p = r * np.cos(nu), r * np.sin(nu)
    h = np.sqrt(MU * p)
    vx_p, vy_p = -MU / h * np.sin(nu), MU / h * (el.e + np.cos(nu))
    cO, sO, co, so, ci, si = np.cos(raan), np.sin(raan), np.cos(argp), np.sin(argp), np.cos(i), np.sin(i)
    # rotation perifocal -> ECI (per time step since raan/argp drift)
    r11, r12 = cO * co - sO * so * ci, -cO * so - sO * co * ci
    r21, r22 = sO * co + cO * so * ci, -sO * so + cO * co * ci
    r31, r32 = so * si, co * si
    pos = np.stack([r11 * x_p + r12 * y_p, r21 * x_p + r22 * y_p, r31 * x_p + r32 * y_p], axis=-1)
    vel = np.stack([r11 * vx_p + r12 * vy_p, r21 * vx_p + r22 * vy_p, r31 * vx_p + r32 * vy_p], axis=-1)
    return pos, vel


def gmst_rad(dt: datetime) -> float:
    jd = dt.timestamp() / 86400.0 + 2440587.5
    T = (jd - 2451545.0) / 36525.0
    g = 280.46061837 + 360.98564736629 * (jd - 2451545.0) + 0.000387933 * T ** 2
    return np.radians(g % 360.0)


def subpoint(pos: np.ndarray, dt: datetime) -> tuple[float, float]:
    x, y, z = pos
    lat = np.degrees(np.arctan2(z, np.hypot(x, y)))
    lon = (np.degrees(np.arctan2(y, x) - gmst_rad(dt)) + 540) % 360 - 180
    return float(lat), float(lon)


def screen(objects: list[dict], days: float = 7.0, coarse_step: float = 60.0, threshold_km: float = 5.0,
           coarse_gate_km: float = 700.0) -> list[dict]:
    """Return conjunctions below threshold_km within the window. Coarse pass at coarse_step, refine local minima
    below coarse_gate_km at 1 s. objects: dicts with object_id and element columns."""
    els = [Elements(float(o["a_km"]), float(o["e"]), float(o["inc_deg"]), float(o["raan_deg"]), float(o["argp_deg"]), float(o["m0_deg"])) for o in objects]
    t = np.arange(0, days * 86400 + coarse_step, coarse_step)
    P = np.stack([propagate(e, t)[0] for e in els])          # (N,T,3)
    N = len(els)
    out = []
    for i in range(N):
        d = np.linalg.norm(P[i + 1:] - P[i][None, :, :], axis=-1)   # (N-i-1, T)
        for jj in range(d.shape[0]):
            j = i + 1 + jj
            dj = d[jj]
            # local minima below the gate
            mins = np.where((dj[1:-1] < dj[:-2]) & (dj[1:-1] <= dj[2:]) & (dj[1:-1] < coarse_gate_km))[0] + 1
            if dj[0] < coarse_gate_km and dj[0] <= dj[1]:
                mins = np.concatenate([[0], mins])
            if len(mins) == 0:
                continue
            mins = mins[np.argsort(dj[mins])][:6]
            best = None
            for k in mins:
                tf = np.arange(max(0.0, t[k] - coarse_step), min(t[-1], t[k] + coarse_step) + 1, 1.0)
                pi, vi = propagate(els[i], tf)
                pj, vj = propagate(els[j], tf)
                dd = np.linalg.norm(pi - pj, axis=-1)
                m = int(np.argmin(dd))
                if best is None or dd[m] < best[0]:
                    best = (float(dd[m]), float(tf[m]), float(np.linalg.norm(vi[m] - vj[m])), pi[m])
            if best and best[0] < threshold_km:
                tca = EPOCH + timedelta(seconds=best[1])
                lat, lon = subpoint(best[3], tca)
                out.append({"a": objects[i]["object_id"], "b": objects[j]["object_id"], "miss_km": round(best[0], 3),
                            "tca": tca.strftime("%Y-%m-%dT%H:%M:%SZ"), "tca_s": best[1], "rel_speed_km_s": round(best[2], 3),
                            "lat": round(lat, 2), "lon": round(lon, 2), "alt_km": round(float(np.linalg.norm(best[3])) - RE, 1)})
    out.sort(key=lambda c: c["miss_km"])
    return out
