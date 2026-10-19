"""python -m whycore.cli ask ["question"]  |  python -m whycore.cli tables  |  python -m whycore.cli sql "SELECT ..." """
from __future__ import annotations
import importlib, json, os, sys


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "ask"
    if cmd == "tables":
        from whycore.data import data
        print("\n".join(data.tables())); return 0
    if cmd == "sql":
        from whycore.data import data
        res = data.run_sql(argv[1]); print(json.dumps(res["rows"][:50], indent=1, default=str)); print(f"-- {res['rows_n']} rows"); return 0
    from whycore.pipeline import Run
    domain = importlib.import_module(os.environ.get("DOMAIN_MODULE", "app.domain")).DOMAIN
    run = Run(domain, argv[1] if len(argv) > 1 else None).execute()
    print(json.dumps(run.to_dict(), indent=1, default=str)); return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
