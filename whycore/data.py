"""One door to data. Every call returns {rows, columns, sql, source, rows_n, elapsed_ms} so the ledger can cite it.

Backends
  zetaris  : GET {ZETARIS_REST}/auth/login (Basic) -> JWT, then POST {ZETARIS_REST}/sql-editor/sqls/run (Bearer,
             X-Org-ID). The hackathon path; bare table names get ZETARIS_PREFIX. Lightning returns every value as a
             string, so values are typed here (bool, int, float) before any domain code sees them.
  postgres : direct psycopg (dev)
  duckdb   : in-process DuckDB over app/data/seed/*.csv (+ app/schema.sql views). Zero infrastructure: the demo and
             CI path. Table name = CSV file stem.
Write SQL that is valid in both DuckDB and Postgres: ANSI joins, CAST, no vendor functions.
"""
from __future__ import annotations
import glob, logging, os, re, time, uuid
from typing import Any
from whycore.settings import settings

log = logging.getLogger("whycore.data")


class DataAccess:
    def __init__(self) -> None:
        self.mode = settings.data_backend
        self._duck = None
        self._ztoken: str | None = None
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
        if self.mode == "zetaris" and settings.zetaris_prefix:
            res = self.run_sql(f"SHOW DATASOURCE TABLES {settings.zetaris_prefix.rstrip('.')}")
            return sorted(str(next(iter(r.values()))) if "name" not in r else str(r["name"]) for r in res["rows"])
        if self.mode == "duckdb":
            return [r["name"] for r in self.run_sql("SELECT table_name AS name FROM information_schema.tables WHERE table_schema='main' ORDER BY 1")["rows"]]
        return [r["name"] for r in self.run_sql("SELECT table_name AS name FROM information_schema.tables WHERE table_schema='public' ORDER BY 1")["rows"]]

    # ---- backends ---------------------------------------------------------------------------------------------
    _TABLE_REF = re.compile(r"\b(FROM|JOIN)(\s+)(?![(])([A-Za-z_][A-Za-z0-9_]*)\b(?!\s*[.(])", re.IGNORECASE)

    def _prefix(self, sql: str) -> str:
        """Qualify bare table names after FROM/JOIN with ZETARIS_PREFIX; leave subqueries and dotted names alone."""
        if not settings.zetaris_prefix:
            return sql
        return self._TABLE_REF.sub(lambda m: f"{m.group(1)}{m.group(2)}{settings.zetaris_prefix}{m.group(3)}", sql)

    @staticmethod
    def _typed(v):
        if not isinstance(v, str):
            return v
        lv = v.lower()
        if lv in ("true", "false"):
            return lv == "true"
        if lv == "null":
            return None
        if re.fullmatch(r"-?(0|[1-9][0-9]*)", v):
            return int(v)
        if re.fullmatch(r"-?(0|[1-9][0-9]*)\.[0-9]+([eE][-+]?[0-9]+)?", v):
            return float(v)
        return v

    def _zetaris_login(self) -> str:
        import httpx
        r = httpx.get(settings.zetaris_rest.rstrip("/") + "/auth/login", auth=(settings.zetaris_user or "", settings.zetaris_password or ""),
                      headers={"X-Org-ID": settings.zetaris_org_id, "X-Request-ID": str(uuid.uuid4())}, timeout=30)
        r.raise_for_status()
        self._ztoken = r.json()["idToken"]
        return self._ztoken

    def _zetaris(self, sql: str):
        import httpx
        url = settings.zetaris_rest.rstrip("/") + "/sql-editor/sqls/run"
        body = {"queryId": str(uuid.uuid4()), "sql": sql, "limit": settings.zetaris_limit, "source": "SqlEditor"}
        for attempt in (0, 1):
            token = self._ztoken or self._zetaris_login()
            r = httpx.post(url, json=body, timeout=180, headers={"Authorization": f"Bearer {token}", "X-Org-ID": settings.zetaris_org_id,
                                                                  "X-Request-ID": str(uuid.uuid4())})
            if r.status_code == 401 and attempt == 0:      # token expired: log in once more
                self._ztoken = None
                continue
            if not r.is_success:
                raise RuntimeError(f"Zetaris HTTP {r.status_code}: {r.text[:500]}")
            break
        js = r.json()
        if isinstance(js, dict) and "data" in js and ("headers" in js or "columns" in js):
            cols = [c["name"] if isinstance(c, dict) else c for c in js.get("headers") or js["columns"]]
            return [dict(zip(cols, map(self._typed, row))) if isinstance(row, list) else row for row in js["data"]], cols
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
