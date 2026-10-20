"""Shared helpers for the scanners: load targets.yaml, append rows to the inventory CSV in the seed schema."""
from __future__ import annotations
import csv, os, sys
from datetime import date
import yaml

HERE = os.path.dirname(__file__)
COLS = ["asset_id", "name", "host", "port", "kind", "algorithm", "key_bits", "purpose", "negotiated_kex", "negotiated_sig",
        "expires", "in_use", "data_class", "traffic_gb_month", "source", "found_at", "note"]
OUT_DIR = os.environ.get("INVENTORY_DIR", os.path.join(HERE, "..", "inventory"))


def targets() -> dict:
    p = os.path.join(HERE, "targets.yaml")
    if not os.path.exists(p):
        sys.exit("create app/data/scanners/targets.yaml from targets.example.yaml (own hosts only)")
    return yaml.safe_load(open(p))


def append(rows: list[dict], source: str) -> str:
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, "assets.csv")
    new = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        if new:
            w.writeheader()
        for i, r in enumerate(rows):
            r.setdefault("asset_id", f"{source[:3].upper()}{int(date.today().strftime('%j')):03d}{i:03d}")
            r.setdefault("source", source); r.setdefault("found_at", date.today().isoformat())
            r.setdefault("in_use", True); r.setdefault("traffic_gb_month", 0)
            w.writerow({c: r.get(c, "") for c in COLS})
    return path
