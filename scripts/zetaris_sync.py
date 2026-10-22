"""Zetaris sync stub.

TODO (Urvashi): apply numbered, append-only SQL migrations in
zetaris/migrations/ through the documented Zetaris REST endpoint, using
ingestion/.env (127.0.0.1, not agents/.env), record a per-machine ledger
at .zetaris-sync/ledger.json, and run verify queries.

See zetaris/README.md. This stub applies nothing.
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    print("zetaris-sync: TODO — not implemented. No SQL was sent.")
    print("Planned: apply zetaris/migrations/NNN_*.sql in order (idempotent).")
    print("Planned env file: ingestion/.env (127.0.0.1). Not agents/.env.")
    print("Planned ledger: .zetaris-sync/ledger.json (git-ignored, per machine).")
    # Do not echo argv. A token passed on the command line must not hit the terminal.
    if args:
        print(f"Arguments ignored by the stub: {len(args)} (values not printed).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
