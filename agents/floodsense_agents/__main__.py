"""Agents service: FastAPI on port 8100 inside the compose network (not published). The API container proxies it and adds
cache, rate limits and replay (Ayush, Mihir). Routes follow the API contract (gameplan v2 §5.5); every response carries
served_from (live | cache | replay) and cached_at.

GET  /health                       service, graph, flags, fakes in use
GET  /config                       flags, lanes, schema, checkpointer (no secrets)
POST /runs                         RunRequest -> runs until the HITL interrupt; returns the run snapshot (status awaiting_approval)
GET  /runs/past                    runs started by this process, newest first (the checkpointer holds every run's state)
GET  /runs/{id}                    snapshot: contract state + claims, evidence, judge_summary, trace
GET  /runs/{id}/approval           what the reviewer sees (409 unless awaiting approval)
POST /runs/{id}/approval           ApprovalDecision {action: approve|edit|reject, edits?, reviewer_note?, reviewer?} -> resumes the run
GET  /runs/{id}/citations          every citation record of the run plus the evidence and provenance they point at
GET  /runs/{id}/events             SSE: TraceEvent json per `trace` event as they happen, then one `status` event

    python -m floodsense_agents            # host: http://127.0.0.1:8100
"""
from __future__ import annotations
import asyncio, json, logging, time
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from floodsense_agents import __version__
from floodsense_agents.models import ApprovalDecision, RunRequest
from floodsense_agents.runtime import NotAwaitingApproval, RunNotFound, Runtime
from floodsense_agents.settings import settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
app = FastAPI(title="FloodSense EU — agents", version=__version__)
_rt: Runtime | None = None


def runtime() -> Runtime:
    global _rt
    if _rt is None:
        _rt = Runtime()
    return _rt


def set_runtime(rt: Runtime) -> None:
    global _rt
    _rt = rt


def _live(body: dict) -> dict:
    body.setdefault("served_from", "live")
    body.setdefault("cached_at", None)
    return body


@app.get("/health")
def health():
    rt = runtime()
    return _live({"status": "ok", "service": "floodsense-agents", "graph": "compiled", "version": __version__,
                  "llm": type(getattr(rt.deps, "llm", None)).__name__ if rt.deps else "injected",
                  "zetaris": type(getattr(rt.deps, "zetaris", None)).__name__ if rt.deps else "injected"})


@app.get("/config")
def config():
    return _live({"flags": {"FF_LIVE_DATA": settings.live_data, "FF_SKEPTIC": settings.ff_skeptic, "FF_JUDGE": settings.ff_judge, "FF_HITL": settings.ff_hitl,
                            "FF_HMEM": settings.ff_hmem, "FF_RAG_DOCS": settings.ff_rag_docs},
                  "lanes": {"fast": settings.model_fast, "deep": settings.model_deep}, "schema": settings.schema,
                  "checkpointer": settings.checkpointer, "skeptic_max_rounds": settings.skeptic_max_rounds, "judge_repair_rounds": settings.judge_repair_rounds,
                  "judge_min_score": settings.judge_min_score, "events": ["EMSR773", "EMSR517"]})


@app.post("/runs", status_code=201)
def start_run(req: RunRequest):
    try:
        return _live(runtime().start(req))
    except KeyError as e:
        raise HTTPException(422, str(e))


@app.get("/runs/past")
def past_runs(limit: int = 50):
    return _live({"runs": runtime().past(limit)})


@app.get("/runs/{run_id}")
def get_run(run_id: str):
    try:
        return _live(runtime().snapshot(run_id))
    except RunNotFound:
        raise HTTPException(404, f"run {run_id} not found")


@app.get("/runs/{run_id}/approval")
def get_approval(run_id: str):
    try:
        return _live(runtime().approval(run_id))
    except RunNotFound:
        raise HTTPException(404, f"run {run_id} not found")
    except NotAwaitingApproval as e:
        raise HTTPException(409, str(e))


@app.post("/runs/{run_id}/approval")
def post_approval(run_id: str, decision: ApprovalDecision):
    if decision.action == "edit" and not (decision.edits or "").strip():
        raise HTTPException(422, "action=edit requires edits")
    try:
        return _live(runtime().resume(run_id, decision))
    except RunNotFound:
        raise HTTPException(404, f"run {run_id} not found")
    except NotAwaitingApproval as e:
        raise HTTPException(409, str(e))


@app.get("/runs/{run_id}/citations")
def get_citations(run_id: str):
    try:
        return _live(runtime().citations(run_id))
    except RunNotFound:
        raise HTTPException(404, f"run {run_id} not found")


@app.get("/runs/{run_id}/events")
async def events(run_id: str):
    rt = runtime()
    try:
        rt.snapshot(run_id)
    except RunNotFound:
        raise HTTPException(404, f"run {run_id} not found")

    async def gen():
        sent, t0 = 0, time.time()
        while time.time() - t0 < 900:
            s = rt.snapshot(run_id)
            for ev in s["trace"][sent:]:
                yield f"event: trace\ndata: {json.dumps(ev)}\n\n"
            sent = len(s["trace"])
            if s["status"] != "running":
                yield f"event: status\ndata: {json.dumps({'run_id': run_id, 'status': s['status'], 'served_from': s['served_from'], 'cached_at': s['cached_at']})}\n\n"
                return
            await asyncio.sleep(0.5)
    return StreamingResponse(gen(), media_type="text/event-stream")


def main() -> None:
    import uvicorn
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")


if __name__ == "__main__":
    main()
