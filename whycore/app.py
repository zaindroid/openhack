"""FastAPI surface shared by every idea. Loads app/domain.py (class `DOMAIN`) and serves one page.

GET  /            the app's own page (app/static/index.html) when it ships one, else the report
GET  /ui/{name}   app/static/{name}.html · GET /report  UI (report) · GET /live the animated live view
GET  /healthz     liveness + backend/model status
GET  /meta        domain title, question, sources, tables
POST /ask         {question?, max_signals?} → full run
GET  /runs        recent run summaries
GET  /runs/{id}   full run
POST /runs/{id}/approve  {action_id, approve}
GET  /view/{name} a domain-declared SQL view (for the data tabs)
GET  /memory      memory stats · DELETE /memory resets it
POST /ask/start   start a run in the background → {run_id}; watch it on GET /events (SSE) and GET /live
GET  /events      Server-Sent Events: every step, query and model call as it happens
GET  /live        the live portal: the agent pipeline at work, animated
"""
from __future__ import annotations
import importlib, os
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel
from whycore import auth, events
from whycore.data import data
from whycore.memory import memory
from whycore.model import model
from whycore.pipeline import Run
from whycore.settings import settings


def load_domain():
    mod = importlib.import_module(os.environ.get("DOMAIN_MODULE", "app.domain"))
    return mod.DOMAIN


DOMAIN = load_domain()
app = FastAPI(title=DOMAIN.title)
app.middleware("http")(auth.middleware)
app.get("/login", response_class=HTMLResponse)(auth.login_page)
app.post("/login")(auth.login)
app.get("/logout")(auth.logout)
RUNS: dict[str, Run] = {}
KEEP_RUNS = int(os.environ.get("KEEP_RUNS", "20"))           # newest runs kept in memory (runs.jsonl keeps every summary)


class Ask(BaseModel):
    question: str | None = None
    max_signals: int | None = None


class Approve(BaseModel):
    action_id: str
    approve: bool = True


@app.get("/healthz")
def healthz():
    return {"ok": True, "domain": DOMAIN.name, "data_backend": data.mode, "model": model.status(), "memory": memory.stats()}


@app.get("/meta")
def meta():
    return {"name": DOMAIN.name, "title": DOMAIN.title, "track": DOMAIN.track, "question": DOMAIN.question,
            "description": DOMAIN.description, "sources": DOMAIN.sources, "views": list(DOMAIN.views.keys()),
            "tables": data.tables(), "table_sources": data.table_sources() if data.mode == "zetaris" else {},
            "extra": DOMAIN.extra_json(data), "data_backend": data.mode, "model": model.status()}


@app.post("/ask")
def ask(body: Ask):
    run = Run(DOMAIN, body.question, body.max_signals).execute()
    RUNS[run.id] = run
    for old in sorted(RUNS.values(), key=lambda r: r.created)[:-KEEP_RUNS]:   # bounded: a scheduled /ask must not grow memory
        RUNS.pop(old.id, None)
    return run.to_dict()


@app.post("/ask/start")
def ask_start(body: Ask):
    """Start a run in a background thread and return at once; progress streams on /events."""
    import threading
    run = Run(DOMAIN, body.question, body.max_signals)
    RUNS[run.id] = run
    for old in sorted(RUNS.values(), key=lambda r: r.created)[:-KEEP_RUNS]:
        RUNS.pop(old.id, None)

    def go():
        try:
            run.execute()
        except Exception as e:
            run.status = f"failed: {str(e)[:200]}"
            events.publish("run", run_id=run.id, status="failed", error=str(e)[:200])
    threading.Thread(target=go, daemon=True, name=f"run-{run.id}").start()
    return {"run_id": run.id, "status": run.status}


@app.get("/events")
def event_stream():
    """SSE feed of everything the agents do; 15 s heartbeats keep proxies from closing the connection."""
    import json, queue

    def gen():
        q = events.subscribe()
        try:
            yield "retry: 2000\n\n"
            while True:
                try:
                    ev = q.get(timeout=15)
                    yield f"data: {json.dumps(ev, default=str)}\n\n"
                except queue.Empty:
                    yield ": ping\n\n"
        finally:
            events.unsubscribe(q)
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/live", response_class=HTMLResponse)
def live():
    here = os.path.dirname(__file__)
    with open(os.path.join(here, "static", "live.html")) as f:
        return f.read()


@app.get("/runs")
def runs():
    return [r.summary() for r in sorted(RUNS.values(), key=lambda r: -r.created)][:50]


@app.get("/runs/{run_id}")
def get_run(run_id: str):
    if run_id not in RUNS:
        raise HTTPException(404, "no such run")
    return RUNS[run_id].to_dict()


@app.post("/runs/{run_id}/approve")
def approve(run_id: str, body: Approve):
    if run_id not in RUNS:
        raise HTTPException(404, "no such run")
    a = RUNS[run_id].approve(body.action_id, body.approve)
    if a is None:
        raise HTTPException(404, "no such action")
    return a


@app.get("/runs/{run_id}/extras/{name}")
def run_extra(run_id: str, name: str):
    """A hook's artefact (e.g. the signed attestation) as downloadable JSON."""
    if run_id not in RUNS or name not in RUNS[run_id].extras:
        raise HTTPException(404, "no such run or extra")
    return JSONResponse(RUNS[run_id].extras[name], headers={"Content-Disposition": f'attachment; filename="{run_id}-{name}.json"'})


@app.get("/view/{name}")
def view(name: str):
    if name not in DOMAIN.views:
        raise HTTPException(404, "no such view")
    res = data.run_sql(DOMAIN.views[name])
    return {"name": name, "sql": res["sql"], "sql_executed": res["sql_executed"], "columns": res["columns"], "rows": res["rows"][:500],
            "rows_n": res["rows_n"]}


@app.get("/memory")
def memory_stats():
    return memory.stats()


@app.delete("/memory")
def memory_reset():
    memory.reset()
    return memory.stats()


def domain_page(name: str) -> str | None:
    """app/static/<name> next to the domain module, if the idea ships its own page."""
    mod = importlib.import_module(type(DOMAIN).__module__)
    p = os.path.join(os.path.dirname(mod.__file__), "static", name)
    return p if os.path.exists(p) else None


@app.get("/", response_class=HTMLResponse)
def index():
    p = domain_page("index.html") or os.path.join(os.path.dirname(__file__), "static", "index.html")
    with open(p, encoding="utf-8") as f:
        return f.read()


@app.get("/ui/{name}", response_class=HTMLResponse)
def ui_page(name: str):
    """Further pages an idea ships in app/static (e.g. /ui/grid → app/static/grid.html)."""
    p = domain_page(name + ".html") if name.replace("-", "").isalnum() else None
    if not p:
        raise HTTPException(404, "no such page")
    with open(p, encoding="utf-8") as f:
        return f.read()


@app.get("/report", response_class=HTMLResponse)
def report():
    with open(os.path.join(os.path.dirname(__file__), "static", "index.html"), encoding="utf-8") as f:
        return f.read()
