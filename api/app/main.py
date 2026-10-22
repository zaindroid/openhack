"""FloodSense EU API.

The UI and the demo call this service (host port 18000). It owns the public contract (gameplan v2 §5.5) and proxies the
run lifecycle to the agents service at AGENTS_URL (http://agents:8100 in compose, http://127.0.0.1:8100 on the host).
Cache, `served_from: cache | replay`, past-run replay and rate limits are later increments (Ayush, Mihir) and slot in
here, in front of the proxy; the agents always answer `served_from: live`.

GET  /health                      this service
GET  /config                      flags and lanes, from the agents
POST /runs                        start a run; returns when the graph pauses for human approval
GET  /runs/past                   earlier runs
GET  /runs/{id}                   run snapshot
GET  /runs/{id}/events            SSE trace stream (proxied as-is)
GET  /runs/{id}/approval          the approval payload (409 unless awaiting approval)
POST /runs/{id}/approval          {action: approve | edit | reject, edits?, reviewer_note?, reviewer?}
GET  /runs/{id}/citations         citation records + evidence + provenance
"""
from __future__ import annotations

import os

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

AGENTS_URL = os.environ.get("AGENTS_URL", "http://127.0.0.1:8100").rstrip("/")
UI_ORIGINS = [o for o in os.environ.get("UI_ORIGINS", "http://localhost:15173,http://127.0.0.1:15173").split(",") if o]
TIMEOUT = httpx.Timeout(600.0, connect=5.0)      # a run waits for the deep lane; the connect timeout stays short

app = FastAPI(title="FloodSense EU", version="0.4.0")
app.add_middleware(CORSMiddleware, allow_origins=UI_ORIGINS, allow_methods=["GET", "POST"], allow_headers=["*"])


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "floodsense-api"}


def _forward(method: str, path: str, body: dict | None = None, params: dict | None = None) -> Response:
    try:
        r = httpx.request(method, f"{AGENTS_URL}{path}", json=body, params=params, timeout=TIMEOUT)
    except httpx.HTTPError as e:
        raise HTTPException(503, f"agents service unreachable at {AGENTS_URL}: {type(e).__name__}")
    return Response(content=r.content, status_code=r.status_code, media_type=r.headers.get("content-type", "application/json"))


@app.get("/config")
def config() -> Response:
    return _forward("GET", "/config")


@app.post("/runs", status_code=201)
async def start_run(request: Request) -> Response:
    return _forward("POST", "/runs", body=await request.json())


@app.get("/runs/past")
def past_runs(limit: int = 50) -> Response:
    return _forward("GET", "/runs/past", params={"limit": limit})


@app.get("/runs/{run_id}")
def get_run(run_id: str) -> Response:
    return _forward("GET", f"/runs/{run_id}")


@app.get("/runs/{run_id}/approval")
def get_approval(run_id: str) -> Response:
    return _forward("GET", f"/runs/{run_id}/approval")


@app.post("/runs/{run_id}/approval")
async def post_approval(run_id: str, request: Request) -> Response:
    return _forward("POST", f"/runs/{run_id}/approval", body=await request.json())


@app.get("/runs/{run_id}/citations")
def get_citations(run_id: str) -> Response:
    return _forward("GET", f"/runs/{run_id}/citations")


@app.get("/runs/{run_id}/events")
async def events(run_id: str) -> StreamingResponse:
    async def gen():
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                async with client.stream("GET", f"{AGENTS_URL}/runs/{run_id}/events") as r:
                    if r.status_code != 200:
                        yield f"event: error\ndata: {{\"status\": {r.status_code}}}\n\n"
                        return
                    async for chunk in r.aiter_text():
                        yield chunk
        except httpx.HTTPError as e:
            yield f"event: error\ndata: {{\"error\": \"agents service unreachable: {type(e).__name__}\"}}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream")
