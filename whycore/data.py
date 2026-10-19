"""One door to data. Every call returns {rows, columns, sql, source, rows_n, elapsed_ms} so the ledger can cite it.

Backends
  zetaris  : POST {ZETARIS_REST}/sql-editor/sqls/run  (the hackathon path; table names get ZETARIS_PREFIX)
  postgres : direct psycopg (dev)
  duckdb   : in-process DuckDB over app/data/seed/*.csv (+ app/schema.sql views). Zero infrastructure: the demo and
             CI path. Table name = CSV file stem.
Write SQL that is valid in both DuckDB and Postgres: ANSI joins, CAST, no vendor functions.
"""
from __future__ import annotations
import glob, logging, os, time
from typing import Any
from whycore.settings import settings

log = logging.getLogger("whycore.data")


class DataAccess:
    def __init__(self) -> None:
        self.mode = settings.data_backend
        self._duck = None
        if self.mode == "zetaris" and not settings.zetaris_rest:
            log.warning("DATA_BACKEND=zetaris but ZETARIS_REST unset: falling back to duckdb")
            self.mode = "duckdb"
        if self.mode == "duckdb":
            self._init_duck()
        log.info("data backend: %s", self.mode)

    # ---- public -----------------------------------------------------------------------------------------------
    def run_sql(self, sql: str, params: dict | None = None) -> dict[str, Any]:
        t0 = time.time()
        if self.mode == "zetaris":
            rows, cols = self._zetaris(self._prefix(sql))
        elif self.mode == "postgres":
            rows, cols = self._postgres(sql, params)
        else:
            rows, cols = self._duckdb(sql, params)
        return {"rows": rows, "columns": cols, "sql": sql, "source": self.mode, "rows_n": len(rows),
                "elapsed_ms": int((time.time() - t0) * 1000)}

    def tables(self) -> list[str]:
        if self.mode == "duckdb":
            return [r["name"] for r in self.run_sql("SELECT table_name AS name FROM information_schema.tables WHERE table_schema='main' ORDER BY 1")["rows"]]
        return [r["name"] for r in self.run_sql("SELECT table_name AS name FROM information_schema.tables WHERE table_schema='public' ORDER BY 1")["rows"]]

    # ---- backends ---------------------------------------------------------------------------------------------
    def _prefix(self, sql: str) -> str:
        return sql if not settings.zetaris_prefix else sql.replace(" FROM ", f" FROM {settings.zetaris_prefix}").replace(" JOIN ", f" JOIN {settings.zetaris_prefix}")

    def _zetaris(self, sql: str):
        import httpx
        url = settings.zetaris_rest.rstrip("/") + "/sql-editor/sqls/run"
        auth = (settings.zetaris_user, settings.zetaris_password) if settings.zetaris_user else None
        r = httpx.post(url, json={"sql": sql}, auth=auth, timeout=120)
        r.raise_for_status()
        js = r.json()
        if isinstance(js, dict) and "data" in js and "columns" in js:
            cols = [c["name"] if isinstance(c, dict) else c for c in js["columns"]]
            return [dict(zip(cols, r)) if isinstance(r, list) else r for r in js["data"]], cols
        if isinstance(js, dict) and "rows" in js:
            rows = js["rows"]; return rows, (list(rows[0].keys()) if rows else [])
        if isinstance(js, list):
            return js, (list(js[0].keys()) if js else [])
        raise RuntimeError(f"unrecognised Zetaris response: {str(js)[:200]}")

    def _postgres(self, sql: str, params: dict | None):
        import psycopg
        from psycopg.rows import dict_row
        with psycopg.connect(settings.database_url, row_factory=dict_row) as conn, conn.cursor() as cur:
            cur.execute(sql, params or {})
            if cur.description is None:
                conn.commit(); return [], []
            rows = [dict(r) for r in cur.fetchall()]
            return rows, [d.name for d in cur.description]

    def _init_duck(self) -> None:
        import duckdb
        self._duck = duckdb.connect(database=":memory:")
        n = 0
        for path in sorted(glob.glob(os.path.join(settings.seed_dir, "*.csv"))):
            name = os.path.splitext(os.path.basename(path))[0]
            self._duck.execute(f'CREATE OR REPLACE TABLE "{name}" AS SELECT * FROM read_csv_auto(?, header=true)', [path])
            n += 1
        if os.path.exists(settings.schema_file):
            with open(settings.schema_file) as f:
                for raw in f.read().split(";"):
                    stmt = "\n".join(l for l in raw.splitlines() if not l.strip().startswith("--")).strip()
                    if stmt.upper().startswith(("CREATE OR REPLACE VIEW", "CREATE VIEW")):
                        try:
                            self._duck.execute(stmt)
                        except Exception as e:  # a view written for Postgres may not parse in DuckDB; say so, keep going
                            log.warning("schema view skipped in duckdb: %s", str(e)[:120])
        log.info("duckdb: %d seed tables from %s", n, settings.seed_dir)

    def _duckdb(self, sql: str, params: dict | None):
        cur = self._duck.execute(sql, params or {}) if params else self._duck.execute(sql)
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = [dict(zip(cols, r)) for r in cur.fetchall()] if cols else []
        return rows, cols


data = DataAccess()
