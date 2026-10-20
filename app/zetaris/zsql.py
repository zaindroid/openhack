"""Run Zetaris Lightning statements through the REST endpoint with whycore's client (one statement per call).

  python app/zetaris/zsql.py "SHOW DATASOURCES"
  python app/zetaris/zsql.py -f app/zetaris/register_sources.sql      # ${VAR} expanded from infra/.env
ZETARIS_* come from infra/.env; ZETARIS_PREFIX is ignored here (statements name their sources)."""
from __future__ import annotations
import os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for line in open(os.path.join(ROOT, "infra", ".env")).read().splitlines():
    if "=" in line and not line.lstrip().startswith("#"):
        k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.strip())
os.environ["DATA_BACKEND"] = "zetaris"; os.environ["ZETARIS_PREFIX"] = ""
sys.path.insert(0, ROOT)
from whycore.data import data  # noqa: E402


def statements(text: str) -> list[str]:
    text = re.sub(r"\$\{(\w+)\}", lambda m: os.environ.get(m.group(1), m.group(0)), text)
    out, cur = [], []
    for line in text.splitlines():
        if line.strip().startswith("--") and not cur:
            continue
        cur.append(line)
        if line.rstrip().endswith(";"):
            out.append("\n".join(cur).strip().rstrip(";")); cur = []
    if "".join(cur).strip():
        out.append("\n".join(cur).strip())
    return out


def main(argv: list[str]) -> int:
    stmts = statements(open(argv[argv.index("-f") + 1]).read()) if "-f" in argv else [argv[0]]
    failed = 0
    for s in stmts:
        print(f">>> {s.splitlines()[0][:110]}")
        try:
            res = data.run_sql(s)
        except Exception as e:
            failed += 1; print("ERROR", str(e)[:400]); continue
        print(" | ".join(res["columns"]))
        for r in res["rows"][:50]:
            print(" | ".join("" if v is None else str(v) for v in r.values()))
        print(f"({res['rows_n']} rows, {res['elapsed_ms']} ms)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
