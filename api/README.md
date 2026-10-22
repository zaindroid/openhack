# API

Purpose: the FastAPI service the UI and the demo call. Planned surface: create a run, stream events (SSE), accept an approval, serve cached or replayed answers with a `cached at HH:MM` label, and rate-limit. This skeleton implements `GET /health` only.

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

Inside compose the process listens on port 8000 and is published on host port 18000. From the repo root, `python tasks.py init-env` copies `.env.example` to `.env` before `up`.

The NVIDIA provider key is not a variable for this service. It lives only in Nightshift's Providers tab.
