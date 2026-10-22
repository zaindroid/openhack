"""Zetaris is the only data path for agents. `run_sql(sql) -> Evidence` is the single call every node uses; the Evidence
it returns is the layer (a) citation (query_id, view, sql, rows_sample, row_count, executed_at_utc).

Live:  POST {ZETARIS_REST_URL}/sql-editor/sqls/run with Authorization: Bearer <API key>, X-Org-ID, fresh X-Request-ID
       (the only documented call, zetaris/README.md). SELECT / WITH only; nothing else leaves this module.
Fake:  the same views as in-memory SQLite (`FakeZetaris`) so the graph, the tests and the UI run before the live views
       exist and on laptops without Zetaris. Rows below are SEED DATA: approximate figures from public reporting on
       Valencia 2024 and Ahr 2021 plus a synthetic insurer portfolio. Urvashi's migrations replace them.

Views, exactly as in the Day-1 contract (gameplan v2 §5.5, views.yaml); schema floodsense_seed.* or floodsense.* via FF_LIVE_DATA:
  hazard_timeline(point_id, ts_utc, rain_mm, discharge_m3s, warning_level)
  discharge_daily(point_id, date, discharge_m3s, source)
  exposure_join(policy_id, site_id, lat, lon, in_footprint, sum_insured_eur, segment)
  provenance(dataset, source_url, publisher, licence, attribution, fetched_at)
The nodes use nothing else, so switching to the live views is FF_LIVE_DATA plus credentials.
"""
from __future__ import annotations
import logging, re, sqlite3, threading, uuid
from datetime import datetime, timezone
from typing import Protocol
import httpx
from floodsense_agents.models import Evidence
from floodsense_agents.settings import settings

log = logging.getLogger("floodsense.zetaris")
_SELECT_ONLY = re.compile(r"^\s*(select|with)\b", re.I)
_VIEW = re.compile(r"\b(?:from|join)\s+([A-Za-z_][\w.]*)", re.I)


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _view_of(sql: str) -> str:
    m = _VIEW.search(sql)
    return m.group(1) if m else "?"


class Zetaris(Protocol):
    def run_sql(self, sql: str) -> Evidence: ...


class ZetarisClient:
    def __init__(self) -> None:
        self.rest = (settings.zetaris_rest_url or "").rstrip("/")
        self._token: str | None = settings.zetaris_api_key

    def _login(self) -> str:
        if settings.zetaris_api_key:
            return settings.zetaris_api_key
        r = httpx.get(f"{self.rest}/auth/login", auth=(settings.zetaris_user or "", settings.zetaris_password or ""),
                      headers={"X-Org-ID": settings.zetaris_org_id, "X-Request-ID": str(uuid.uuid4())}, timeout=30)
        r.raise_for_status()
        self._token = r.json()["idToken"]
        return self._token

    def run_sql(self, sql: str) -> Evidence:
        if not _SELECT_ONLY.match(sql):
            raise ValueError("agents may only run SELECT / WITH statements")
        qid = str(uuid.uuid4())
        body = {"queryId": qid, "sql": sql, "limit": settings.zetaris_row_limit, "source": "SqlEditor"}
        try:
            for attempt in (0, 1):
                token = self._token or self._login()
                r = httpx.post(f"{self.rest}/sql-editor/sqls/run", json=body, timeout=180,
                               headers={"Authorization": f"Bearer {token}", "X-Org-ID": settings.zetaris_org_id, "X-Request-ID": str(uuid.uuid4())})
                if attempt == 0 and not settings.zetaris_api_key and r.status_code in (401, 403):
                    self._token = None
                    continue
                if not r.is_success:
                    raise RuntimeError(f"Zetaris HTTP {r.status_code}: {r.text[:300]}")
                break
            rows = self._rows(r.json())
            return Evidence(query_id=qid, view=_view_of(sql), sql=sql, rows_sample=rows[:20], row_count=len(rows), executed_at_utc=now_utc())
        except Exception as e:
            log.warning("zetaris query failed: %s", str(e)[:200])
            return Evidence(query_id=qid, view=_view_of(sql), sql=sql, rows_sample=[], row_count=0, executed_at_utc=now_utc(), error=str(e)[:300])

    @staticmethod
    def _rows(js) -> list[dict]:
        if isinstance(js, dict) and "data" in js:
            cols = [c["name"] if isinstance(c, dict) else c for c in (js.get("headers") or js.get("columns") or [])]
            return [dict(zip(cols, r)) if isinstance(r, list) else r for r in js["data"]]
        if isinstance(js, dict) and "rows" in js:
            return js["rows"]
        return js if isinstance(js, list) else []


# ---------------------------------------------------------------------------------------------------------------------
# Fake Zetaris: the contract views in SQLite. ATTACH gives `floodsense_seed.<view>` names so the nodes' SQL is identical.
# ---------------------------------------------------------------------------------------------------------------------
_DDL = """
CREATE TABLE {s}.hazard_timeline(point_id TEXT, ts_utc TEXT, rain_mm REAL, discharge_m3s REAL, warning_level TEXT);
CREATE TABLE {s}.discharge_daily(point_id TEXT, date TEXT, discharge_m3s REAL, source TEXT);
CREATE TABLE {s}.exposure_join(policy_id TEXT, site_id TEXT, lat REAL, lon REAL, in_footprint INTEGER, sum_insured_eur REAL, segment TEXT);
CREATE TABLE {s}.provenance(dataset TEXT, source_url TEXT, publisher TEXT, licence TEXT, attribution TEXT, fetched_at TEXT);
"""

# Valencia 29 Oct 2024 (seed, approximate): AEMET reported ~491 mm in ~8 h at Chiva and ~185 mm in one hour at Turís;
# CHJ estimated the Poyo ravine peak above 2,000 m3/s around 17:55 UTC, sensor failed after 1,686 m3/s at 16:45 UTC;
# AEMET red warning 06:30 UTC; ES-Alert to phones 19:11 UTC. Ahr 2021: Altenahr > 5.7 m on 14 Jul evening, gauge failed;
# DWD 100-150 mm / 24 h; discharge estimated ~1,000 m3/s.
_CHIVA = [(9, 18), (10, 35), (11, 52), (12, 70), (13, 88), (14, 96), (15, 74), (16, 58), (17, 31), (18, 12)]
_TURIS = [(13, 20), (14, 42), (15, 71), (16, 185), (17, 60), (18, 15)]
_POYO = [(12, 6), (13, 9), (14, 40), (15, 310), (16, 1686), (17, 2282), (18, None)]
_SEED = {
    "hazard_timeline": [("chiva", f"2024-10-29T{h:02d}:00:00Z", mm, None, "red" if h >= 7 else None) for h, mm in _CHIVA]
                       + [("turis", f"2024-10-29T{h:02d}:00:00Z", mm, None, "red") for h, mm in _TURIS]
                       + [("poyo-ribaroja", f"2024-10-29T{h:02d}:00:00Z", None, q, "es-alert" if h >= 19 else None) for h, q in _POYO]
                       + [("poyo-ribaroja", "2024-10-29T19:11:00Z", None, None, "es-alert")]
                       + [("ahrweiler", "2021-07-14T14:00:00Z", 38.0, None, "3"), ("ahrweiler", "2021-07-14T16:00:00Z", 61.0, None, "4"),
                          ("ahrweiler", "2021-07-14T18:00:00Z", 43.0, None, "4"),
                          ("altenahr", "2021-07-13T06:00:00Z", None, 8.2, None), ("altenahr", "2021-07-14T19:00:00Z", None, 1000.0, "4"),
                          ("altenahr", "2021-07-14T20:00:00Z", None, None, "4")],
    "discharge_daily": [("poyo-ribaroja", "2024-10-28", 3.0, "GloFAS via Open-Meteo"), ("poyo-ribaroja", "2024-10-29", 2100.0, "GloFAS via Open-Meteo"),
                        ("poyo-ribaroja", "2024-10-30", 240.0, "GloFAS via Open-Meteo"),
                        ("altenahr", "2021-07-13", 8.0, "GloFAS via Open-Meteo"), ("altenahr", "2021-07-14", 1000.0, "GloFAS via Open-Meteo"),
                        ("altenahr", "2021-07-15", 210.0, "GloFAS via Open-Meteo")],
    # synthetic portfolio of the demo insurer around the EMSR773 footprint (in_footprint from the Copernicus layer)
    "exposure_join": [("P-1001", "S-001", 39.4275, -0.4178, 1, 4_200_000, "warehouse"), ("P-1002", "S-002", 39.4036, -0.4039, 1, 1_900_000, "retail"),
                      ("P-1003", "S-003", 39.4215, -0.3906, 1, 6_500_000, "retail"), ("P-1004", "S-004", 39.4280, -0.3850, 1, 800_000, "retail"),
                      ("P-1005", "S-005", 39.4370, -0.4680, 1, 3_100_000, "industrial"), ("P-1006", "S-006", 39.4360, -0.4350, 1, 2_400_000, "healthcare"),
                      ("P-1007", "S-007", 39.4720, -0.7200, 0, 1_200_000, "industrial"), ("P-1008", "S-008", 39.4699, -0.3763, 0, 9_000_000, "office"),
                      ("P-1009", "S-009", 39.1900, -0.4350, 1, 2_700_000, "industrial"), ("P-1010", "S-010", 39.4600, -0.3300, 0, 1_500_000, "hospitality")],
    "provenance": [("hazard_timeline", "https://opendata.aemet.es", "AEMET", "AEMET OpenData terms (to confirm)", "© AEMET", "2026-10-22"),
                   ("hazard_timeline", "https://saih.chj.es", "SAIH Júcar (CHJ)", "to verify", "SAIH Júcar / Confederación Hidrográfica del Júcar", "2026-10-22"),
                   ("discharge_daily", "https://open-meteo.com/en/docs/flood-api", "Open-Meteo / GloFAS", "CC BY 4.0", "Weather data by Open-Meteo.com", "2026-10-22"),
                   ("exposure_join", "https://emergency.copernicus.eu/mapping/list-of-components/EMSR773", "Copernicus EMS", "Copernicus terms",
                    "Generated using Copernicus Emergency Management Service information 2024", "2026-10-22"),
                   ("exposure_join", "https://www.openstreetmap.org", "OpenStreetMap", "ODbL", "© OpenStreetMap contributors", "2026-10-22"),
                   ("exposure_join", None, "FloodSense (synthetic portfolio)", "n/a", "Synthetic insurer portfolio, clearly labelled", "2026-10-22")],
}


class FakeZetaris:
    def __init__(self) -> None:
        self._conn = sqlite3.connect(":memory:", check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        for schema in ("floodsense_seed", "floodsense"):
            self._conn.execute(f"ATTACH DATABASE ':memory:' AS {schema}")
            self._conn.executescript(_DDL.format(s=schema))
            for table, rows in _SEED.items():
                self._conn.executemany(f"INSERT INTO {schema}.{table} VALUES ({','.join('?' * len(rows[0]))})", rows)
        self._conn.commit()

    def run_sql(self, sql: str) -> Evidence:
        if not _SELECT_ONLY.match(sql):
            raise ValueError("agents may only run SELECT / WITH statements")
        qid = str(uuid.uuid4())
        try:
            with self._lock:
                rows = [dict(r) for r in self._conn.execute(sql).fetchall()]
            return Evidence(query_id=qid, view=_view_of(sql), sql=sql, rows_sample=rows[:20], row_count=len(rows), executed_at_utc=now_utc(), source="zetaris-fake")
        except sqlite3.Error as e:
            return Evidence(query_id=qid, view=_view_of(sql), sql=sql, rows_sample=[], row_count=0, executed_at_utc=now_utc(), source="zetaris-fake", error=str(e))


def build_zetaris() -> Zetaris:
    if settings.zetaris_mode == "fake" or (settings.zetaris_mode == "auto" and not settings.zetaris_rest_url):
        log.warning("Zetaris: ZETARIS_REST_URL unset -> FakeZetaris (SQLite seed views)")
        return FakeZetaris()
    return ZetarisClient()
