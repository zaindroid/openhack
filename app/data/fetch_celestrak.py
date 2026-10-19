"""Fetch live general-perturbation element sets from CelesTrak (free, no key) into app/data/seed/objects.csv.

    python3 app/data/fetch_celestrak.py [--group active|starlink|cosmos-1408-debris|...] [--limit N] [--out PATH]

CelesTrak GP JSON fields used: NORAD_CAT_ID, OBJECT_NAME, OBJECT_ID (intl designator), EPOCH, MEAN_MOTION (rev/day),
ECCENTRICITY, INCLINATION, RA_OF_ASC_NODE, ARG_OF_PERICENTER, MEAN_ANOMALY, OBJECT_TYPE (PAYLOAD | ROCKET BODY | DEBRIS |
UNKNOWN). Mean motion → semi-major axis: a = (mu / n^2)^(1/3) with n in rad/s.

Owner and country are NOT in GP data: they come from the UN register / Space-Track SATCAT (fetch_unoosa.py); this script
leaves them "unknown" so the Skeptic marks owner-based tests uncertain rather than guessing. All elements are rebased to
a common epoch with their own mean motion (fine for screening; real operations use SGP4 per TLE — see app/requirements.txt).

Needs internet. Writes real data: the UI description should then be changed from "illustrative" to the fetch date.
"""
from __future__ import annotations
import argparse, csv, json, math, os, sys, urllib.request
from datetime import datetime, timezone

MU = 398600.4418
RE = 6378.137
URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP={group}&FORMAT=json"
TYPE_MAP = {"PAYLOAD": "payload", "ROCKET BODY": "rocket_body", "DEBRIS": "debris", "UNKNOWN": "unknown"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", default="active")
    ap.add_argument("--limit", type=int, default=400, help="objects to keep (screening is O(N^2))")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed", "objects.csv"))
    ap.add_argument("--epoch", default=None, help="common epoch ISO (default: now, UTC)")
    args = ap.parse_args()
    epoch = datetime.fromisoformat(args.epoch).astimezone(timezone.utc) if args.epoch else datetime.now(timezone.utc).replace(microsecond=0)
    with urllib.request.urlopen(URL.format(group=args.group), timeout=60) as r:
        gp = json.load(r)
    rows = []
    for g in gp[: args.limit]:
        n = float(g["MEAN_MOTION"]) * 2 * math.pi / 86400.0
        a = (MU / n ** 2) ** (1 / 3)
        e = float(g["ECCENTRICITY"])
        ep = datetime.fromisoformat(g["EPOCH"]).replace(tzinfo=timezone.utc)
        dt = (epoch - ep).total_seconds()
        m0 = (float(g["MEAN_ANOMALY"]) + math.degrees(n * dt)) % 360    # rebase mean anomaly to the common epoch
        rows.append({
            "object_id": str(g["NORAD_CAT_ID"]), "name": g["OBJECT_NAME"], "type": TYPE_MAP.get(g.get("OBJECT_TYPE", "UNKNOWN"), "unknown"),
            "owner": "unknown", "country": "", "manoeuvrable": "true" if TYPE_MAP.get(g.get("OBJECT_TYPE", "")) == "payload" else "false",
            "launch_year": g.get("OBJECT_ID", "")[:4], "parent_event": "", "mass_kg": "",
            "epoch": epoch.strftime("%Y-%m-%dT%H:%M:%SZ"), "a_km": round(a, 4), "e": e, "inc_deg": g["INCLINATION"],
            "raan_deg": g["RA_OF_ASC_NODE"], "argp_deg": g["ARG_OF_PERICENTER"], "m0_deg": round(m0, 4),
            "perigee_km": round(a * (1 - e) - RE, 1), "apogee_km": round(a * (1 + e) - RE, 1),
        })
    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    print(f"wrote {len(rows)} objects from CelesTrak group '{args.group}' to {args.out} (epoch {epoch.isoformat()})")
    print("owner/country/manoeuvrable are placeholders until fetch_unoosa.py (or a SATCAT export) fills them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
