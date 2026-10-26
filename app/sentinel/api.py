"""The sentinel in the vault: sweeps and findings read through Zetaris, changes streamed on /events, decisions recorded.

GET  /sentinel            hosts (last sweep per host) and findings, with the statements that read them
GET  /sentinel/decisions  vault decisions on findings, for the collector (app/sentinel/sweep.py) to fold into baselines
POST /sentinel/decide     {finding_id, decision: expected | incident}: a human decision; nothing on a host is changed
POST /sentinel/ping       the collector published a sweep: read it now instead of at the next minute

The collector writes Parquet to MinIO; this module only reads mosca_s3.sentinel_sweeps / mosca_s3.sentinel_findings
through Zetaris, like every other number in the vault."""
from __future__ import annotations
import threading, time
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from whycore import events
from whycore.data import data
from whycore.memory import memory

router = APIRouter()
SQL_SWEEPS = "SELECT * FROM mosca_s3.sentinel_sweeps ORDER BY host"
SQL_FINDINGS = "SELECT * FROM mosca_s3.sentinel_findings"
EVERY_S = 60
STATE: dict = {"hosts": [], "findings": [], "read_at": None, "error": None, "sql": [SQL_SWEEPS, SQL_FINDINGS], "sql_executed": []}
_wake = threading.Event()
_lock = threading.Lock()
DECISIONS = ("expected", "incident")


def _key(fid: str) -> str:
    return "sentinel-" + fid


def refresh() -> None:
    if data.mode != "zetaris":
        STATE["error"] = f"the sentinel reads Zetaris; this instance runs on {data.mode}"
        return
    try:
        s, f = data.run_sql(SQL_SWEEPS), data.run_sql(SQL_FINDINGS)
    except Exception as e:
        STATE["error"] = str(e)[:200]
        return
    with _lock:
        first = STATE["read_at"] is None
        old_sw = {h["host"]: h["sweep_time"] for h in STATE["hosts"]}
        old_f = {x["finding_id"]: x["status"] for x in STATE["findings"]}
        fnd = f["rows"]
        for x in fnd:      # an all-digit id comes back from Zetaris as a number
            x["finding_id"] = str(x["finding_id"])
        for x in fnd:      # decided in the vault, not yet folded by the collector
            d = memory.decision(_key(x["finding_id"]), x["finding_id"])
            if d and x["status"] == "open":
                x["status"] = d["status"]
        STATE.update(hosts=s["rows"], findings=fnd, read_at=time.time(), error=None, sql_executed=[s["sql_executed"], f["sql_executed"]])
    if first:
        return
    for h in s["rows"]:
        if old_sw.get(h["host"]) != h["sweep_time"]:
            events.publish("sentinel", what="sweep", host=h["host"], sweep_time=h["sweep_time"], open=h["open_findings"], probe_s=h["probe_s"])
    for x in fnd:
        if x["status"] == "open" and old_f.get(x["finding_id"]) != "open":
            events.publish("sentinel", what="finding", host=x["host"], finding_id=x["finding_id"], severity=x["severity"], check=x["check"], title=x["title"])


def _loop() -> None:
    while True:
        try:
            refresh()
        except Exception as e:
            STATE["error"] = str(e)[:200]
        _wake.wait(EVERY_S)
        _wake.clear()


threading.Thread(target=_loop, daemon=True, name="sentinel-reader").start()


@router.get("/sentinel")
def sentinel():
    return {**STATE, "age_s": round(time.time() - STATE["read_at"], 1) if STATE["read_at"] else None}


@router.get("/sentinel/decisions")
def decisions():
    out = []
    for x in STATE["findings"]:
        d = memory.decision(_key(x["finding_id"]), x["finding_id"])
        if d:
            out.append({"finding_id": x["finding_id"], "decision": d["status"], "t": d["t"]})
    return out


class Decide(BaseModel):
    finding_id: str
    decision: str


@router.post("/sentinel/decide")
def decide(body: Decide):
    if body.decision not in DECISIONS:
        raise HTTPException(400, "decision is expected or incident")
    with _lock:
        x = next((x for x in STATE["findings"] if x["finding_id"] == body.finding_id), None)
        if not x:
            raise HTTPException(404, "no such finding")
        memory.record_decision(_key(x["finding_id"]), x["finding_id"], body.decision, "sentinel")
        x["status"] = body.decision
    events.publish("sentinel", what="decided", host=x["host"], finding_id=x["finding_id"], decision=body.decision, title=x["title"])
    return x


@router.post("/sentinel/ping")
def ping():
    _wake.set()
    return {"ok": True}
