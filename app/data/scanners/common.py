"""Shared helpers for the scanners: load targets.yaml, write rows to the inventory CSV in the seed schema.

asset_id is stable across re-scans: <source prefix>-<sha1(kind|host|port|name)[:8]>, so evals, approvals and the CBOM
can refer to the same asset next week. Each scanner replaces its own previous rows (same `source`) instead of
appending duplicates; rows from the other scanners are kept."""
from __future__ import annotations
import csv, hashlib, os, sys
from datetime import date
import yaml

HERE = os.path.dirname(__file__)
COLS = ["asset_id", "name", "host", "port", "kind", "algorithm", "key_bits", "purpose", "negotiated_kex", "negotiated_sig",
        "expires", "in_use", "data_class", "traffic_gb_month", "source", "found_at", "note"]
OUT_DIR = os.environ.get("INVENTORY_DIR", os.path.join(HERE, "..", "inventory"))
PREFIX = {"tls_scan": "TLS", "ssh_scan": "SSH", "ct_log": "CT", "repo_scan": "REPO", "firmware_scan": "FW"}


def targets() -> dict:
    p = os.environ.get("TARGETS", os.path.join(HERE, "targets.yaml"))
    if not os.path.exists(p):
        sys.exit("create app/data/scanners/targets.yaml from targets.example.yaml (own hosts only)")
    return yaml.safe_load(open(p))


def asset_id(source: str, r: dict) -> str:
    key = f"{r.get('kind')}|{r.get('host')}|{r.get('port')}|{r.get('name')}"
    return f"{PREFIX.get(source, source[:4].upper())}-{hashlib.sha1(key.encode()).hexdigest()[:8]}"


def append(rows: list[dict], source: str) -> str:
    """Write this scanner's rows, replacing its rows from an earlier scan. Name kept for the scanners' call sites."""
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, "assets.csv")
    kept = []
    if os.path.exists(path):
        with open(path, newline="") as f:
            kept = [r for r in csv.DictReader(f) if r.get("source") != source]
    seen = {r["asset_id"] for r in kept}
    out = list(kept)
    for r in rows:
        r.setdefault("source", source); r.setdefault("found_at", date.today().isoformat())
        r.setdefault("in_use", True); r.setdefault("traffic_gb_month", 0)
        r.setdefault("asset_id", asset_id(source, r))
        if r["asset_id"] in seen:          # same asset reported twice in one scan: keep the first
            continue
        seen.add(r["asset_id"])
        out.append({c: r.get(c, "") for c in COLS})
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(out)
    return path


def log_probe(source: str, target: str, outcome: str) -> None:
    """Targets that were probed but yielded no public-key asset (no TLS, unreachable, refused) go to probes.csv, so the
    inventory's gaps are as traceable as its rows."""
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, "probes.csv")
    rows = []
    if os.path.exists(path):
        with open(path, newline="") as f:
            rows = [r for r in csv.DictReader(f) if not (r["source"] == source and r["target"] == target)]
    rows.append({"source": source, "target": target, "outcome": outcome, "probed_at": date.today().isoformat()})
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["source", "target", "outcome", "probed_at"])
        w.writeheader()
        w.writerows(rows)
