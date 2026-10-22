# UI

Purpose: the insurer console (map, causal chain, Skeptic verdicts, Judge scores, evidence drawer, approve / edit / reject). This skeleton is a Vite + React + TypeScript placeholder so the compose service has something to build. It does not call the API.

Owner: Mihir until LangGraph and human-in-the-loop are done, then Zain. Anyone who finishes a slot early can pick up UI work. Announce it at stand-up.

From the repo root, `python tasks.py init-env` copies `ui/.env.example` when `ui/.env` is missing. Or, in this directory:

```powershell
Copy-Item .env.example .env
npm install
npm run dev
```

```bash
cp .env.example .env
npm install
npm run dev
```

`npm run build` uses `&&` inside the npm script. npm runs that through `cmd.exe` on Windows, where `&&` works. Do not paste that script into PowerShell 5, which has no `&&`.

Compose publishes the dev server on host port 15173 (container port 5173). `VITE_API_URL` defaults to `http://localhost:18000`, which is the API as the browser sees it.

Do not put tokens in this env file. Vite exposes `VITE_*` values to the browser. The NVIDIA provider key lives only in Nightshift's Providers tab.

Cached or replayed answers, when the console exists, are labelled `cached at HH:MM` and are never shown as live.
