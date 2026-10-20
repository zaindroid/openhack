"""Fill traffic_gb_month for TLS assets from Docker's own counters on the host that runs the containers.

Per running container: NET I/O (rx + tx) since start from `docker stats --no-stream`, divided by uptime and scaled to
30 days, attributed to every hostname in the container's Traefik router rules (Host(`...`)). An edge row gets the sum
of the containers serving its hostname; the Traefik origin row (127.0.0.1:443) gets the sum over all Traefik-routed
containers. Rows with no matching container keep 0 and say so in the note. Use this when Cloudflare zone analytics
are not readable with the available token; it measures container traffic, not edge bytes.

    python app/data/scanners/traffic_docker.py      # rewrites app/data/inventory/assets.csv in place"""
from __future__ import annotations
import csv, json, os, re, subprocess
from datetime import datetime, timezone
from common import COLS, OUT_DIR

UNIT = {"B": 1, "kB": 1e3, "KB": 1e3, "KiB": 1024, "MB": 1e6, "MiB": 1024 ** 2, "GB": 1e9, "GiB": 1024 ** 3, "TB": 1e12}


def to_bytes(s: str) -> float:
    m = re.match(r"([\d.]+)\s*([A-Za-z]+)", s.strip())
    return float(m.group(1)) * UNIT.get(m.group(2), 1) if m else 0.0


def containers() -> dict[str, dict]:
    stats = subprocess.run(["docker", "stats", "--no-stream", "--format", "{{json .}}"], capture_output=True, text=True, timeout=120).stdout
    out = {}
    for ln in stats.splitlines():
        s = json.loads(ln)
        rx, tx = s["NetIO"].split("/")
        ins = json.loads(subprocess.run(["docker", "inspect", s["Name"]], capture_output=True, text=True, timeout=30).stdout)[0]
        started = datetime.fromisoformat(ins["State"]["StartedAt"][:19]).replace(tzinfo=timezone.utc)
        days = max((datetime.now(timezone.utc) - started).total_seconds() / 86400, 1 / 24)
        hosts = set()
        for k, v in (ins["Config"].get("Labels") or {}).items():
            if k.startswith("traefik.http.routers.") and k.endswith(".rule"):
                hosts |= set(re.findall(r"Host\(`([^`]+)`\)", v))
        out[s["Name"]] = {"gb_month": (to_bytes(rx) + to_bytes(tx)) / 1e9 / days * 30, "days": days, "hosts": hosts}
    return out


def main() -> None:
    path = os.path.join(OUT_DIR, "assets.csv")
    rows = list(csv.DictReader(open(path, newline="")))
    cs = containers()
    routed = {n: c for n, c in cs.items() if c["hosts"]}
    for r in rows:
        if r["kind"] != "tls":
            continue
        host = r["host"]
        r["note"] = r["note"].split("; traffic:")[0]          # idempotent on re-runs
        if r["name"].startswith("origin Traefik") and r["port"] == "443":
            gb = sum(c["gb_month"] for c in routed.values())
            r["traffic_gb_month"] = round(gb, 3)
            r["note"] += f"; traffic: docker NET I/O of {len(routed)} Traefik-routed containers, scaled to 30 d"
            continue
        match = {n: c for n, c in routed.items() if host in c["hosts"]}
        if match:
            r["traffic_gb_month"] = round(sum(c["gb_month"] for c in match.values()), 3)
            r["note"] += "; traffic: docker NET I/O of " + ",".join(f"{n[:24]} ({c['days']:.1f} d up)" for n, c in match.items()) + ", scaled to 30 d"
        elif r["name"].startswith("edge "):
            r["note"] += "; traffic: no container metric on servingz for this host (0 = unknown)"
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    print(f"{len(routed)} Traefik-routed containers; updated {path}")


if __name__ == "__main__":
    main()
