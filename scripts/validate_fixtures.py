"""Every fixture must parse, carry served_from + generated_at, and never expose an aggregate with n < 5."""
import json, sys
from pathlib import Path
root = Path(__file__).resolve().parents[1] / "fixtures"
bad = []
for p in sorted(root.glob("*.json")):
    d = json.loads(p.read_text(encoding="utf-8"))
    if p.name.endswith("_request.json"):
        continue
    if "served_from" not in d or "generated_at" not in d:
        bad.append(f"{p.name}: missing served_from/generated_at")
    if "n" in d and isinstance(d["n"], int) and d["n"] < 5:
        bad.append(f"{p.name}: aggregate with n < 5")
print("\n".join(bad) or f"{len(list(root.glob('*.json')))} fixtures ok")
sys.exit(1 if bad else 0)
