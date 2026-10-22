# API

Purpose: the FastAPI service the UI and the demo call. It owns the public contract (gameplan §5.5) and proxies the run lifecycle to the agents service at `AGENTS_URL`: `POST /runs`, `GET /runs/past`, `GET /runs/{id}`, `GET /runs/{id}/events` (SSE), `GET|POST /runs/{id}/approval`, `GET /runs/{id}/citations`, `GET /config`, `GET /health`. Every response carries `served_from` and `cached_at`. Cache, replay and rate limits (Ayush, Mihir) slot in here, in front of the proxy. CORS is open to the UI origins only (`UI_ORIGINS`, default `http://localhost:15173,http://127.0.0.1:15173`).

Owner: Zain (runs, SSE, approval) and Ayush (cache and past runs). Mihir adds rate limits.

PowerShell, from this directory. `python -m uvicorn` avoids the `Scripts` vs `bin` difference. `curl` in PowerShell is not curl.

```powershell
py -m pip install -r requirements.txt
py -m uvicorn app.main:app --reload --port 8000
Invoke-RestMethod http://127.0.0.1:8000/health
```

bash:

```bash
python3 -m pip install -r requirements.txt
python3 -m uvicorn app.main:app --reload --port 8000
curl -s http://127.0.0.1:8000/health
```

Inside compose the process listens on port 8000 and is published on host port 18000. On the host, run `python -m floodsense_agents` from `agents/` first and set `AGENTS_URL=http://127.0.0.1:8100` (the default). From the repo root, `python tasks.py init-env` copies `.env.example` to `.env` before `up`.

The NVIDIA provider key is not a variable for this service. It lives only in Nightshift's Providers tab.
