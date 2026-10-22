# FloodSense EU

Europe-centric flood-risk agent for the Open Agent Hackathon 2026 (22–27 Oct, Track 02). It explains why an area is at risk, with cited, grounded claims. A Skeptic challenges the chain, an LLM-as-a-Judge scores it, and a human approves any outbound action.

The playbook is [docs/GAMEPLAN.md](docs/GAMEPLAN.md). Path ownership is [docs/OWNERSHIP.md](docs/OWNERSHIP.md).

## Team

Five peers. The Architect is one role among them, not a team lead.

| Person | Role |
| --- | --- |
| Mihir | Architect: architecture, docs and ADRs, CI/CD, security review. Judge with Zain. UI until Zain is free. |
| Urvashi | Zetaris: ingestion, migrations, vector-search research. |
| Saleeta | Ingestion with Urvashi, citation pipeline, slide deck and demo. |
| Ayush | Meterless Nightshift client, H-MEM, World Model, memory, embeddings, answer cache. |
| Zain | LangGraph agents, human-in-the-loop, LLM-as-a-Judge with Mihir, then the UI. |

## Quick start

You need Python 3.10+ and Docker Desktop. You do not need Make, WSL, or Git Bash. Tasks live in `tasks.py` (stdlib only):

```text
python tasks.py <command>
py tasks.py <command>
```

`py` is the Windows launcher. `python` or `python3` is the same script. Run one command per line. PowerShell 5.x does not support `&&`.

Zetaris (UI `:3000`, REST `:8888/api/v1.0`, JDBC `:10000`) and Nightshift (`http://127.0.0.1:8088/v1`) are each person's own processes. This repository does not start them.

PowerShell 5.x or 7:

```powershell
py tasks.py init-env
py tasks.py up
Invoke-RestMethod http://127.0.0.1:18000/health
py tasks.py down
```

bash (macOS or Linux):

```bash
python3 tasks.py init-env
python3 tasks.py up
curl -s http://127.0.0.1:18000/health
python3 tasks.py down
```

`init-env` copies each missing `.env.example` to `.env` and does not overwrite a file that is already there. Fill `agents/.env` and `ingestion/.env` locally. In PowerShell, `curl` is an alias of `Invoke-WebRequest` and does not accept `-s`. Use `Invoke-RestMethod`, or `curl.exe` if you want the real curl.

`up` builds and starts the API (`127.0.0.1:18000`), the agent runtime (no host port), and the UI (`127.0.0.1:15173`). Published ports bind to loopback. It refuses to start until `api/.env`, `agents/.env`, and `ui/.env` exist. Optional profiles:

```powershell
py tasks.py up-all
```

```bash
python3 tasks.py up-all
```

That adds pgvector on `127.0.0.1:15432` and Redis on `127.0.0.1:16379`. `init-env` also copies `pgvector/.env.example`. `down` stops this project only, including those profiles, even when `pgvector/.env` was never created. It does not remove volumes and it does not stop Zetaris.

Compose is always `docker compose -p floodsense-app` with this repo's `compose.yaml`. An exported `COMPOSE_PROJECT_NAME` or `COMPOSE_FILE` cannot point the task script at another Compose project. If you run `docker compose` yourself, pass the same `-p`.

`zetaris-sync` is a stub. It prints a TODO and applies no SQL. When it is implemented it should read `ingestion/.env` (`127.0.0.1`), not `agents/.env`. `test` compiles the Python packages and runs the unit tests with the current interpreter. Install API deps into a virtualenv first, then run `test` with that interpreter.

PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r api\requirements.txt
.\.venv\Scripts\python.exe tasks.py test
```

bash:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r api/requirements.txt
.venv/bin/python tasks.py test
```

Calling the venv interpreter directly avoids PowerShell's script execution policy, which can block `Activate.ps1`. `lint` is a TODO until the CI branch.

Containers call Zetaris and Nightshift at `host.docker.internal` (`agents/.env`). Host-side scripts use `127.0.0.1` (`ingestion/.env`, and the host-side copies in the root `.env`). The root file is not injected into containers. `host.docker.internal` is wired with `extra_hosts: host-gateway` so Linux and WSL Docker Engine can resolve it. Docker Desktop on Windows already resolves that name. A service bound only to `127.0.0.1` on the host may still be unreachable from a container; that check is Ayush and Urvashi's.

## Layout

| Path | Purpose | Owner |
| --- | --- | --- |
| `ingestion/` | Fetch and stage datasets, seed content | Urvashi, Saleeta |
| `zetaris/migrations/` | Numbered, append-only, idempotent SQL | Urvashi |
| `agents/` | LangGraph package: investigator, skeptic, judge, HITL placeholders | Ayush, Zain |
| `api/` | FastAPI. `/health` only | Zain, Ayush |
| `ui/` | Vite + React + TSX placeholder | Mihir, then Zain |
| `infra/` | How local compose stays off the Zetaris stack | Mihir |
| `tasks.py` | Cross-platform task runner (`up`, `down`, `test`, …) | Mihir |
| `docs/` | Gameplan, ownership, ADRs | Mihir |

## Branching

`main` is the integration branch. This skeleton is that base. Further work lands on short-lived branches (`feat/<area>-<topic>`, `fix/…`, `chore/…`) through pull requests, with one review from outside the pair. Release tags are `v0.x` (increments), `v0.x.y` (fixes), and `v1.0.0-rc.N` (candidates). Tags are not moved. See the gameplan for the increment list. GitHub Actions is a later feature branch, not part of this commit.

## Secrets

- Commit `.env.example` only. `.env` and `.env.*` are git-ignored.
- Zetaris keys and the Nightshift runtime token are created per person and stay in that person's env file.
- The NVIDIA provider key lives only in Nightshift's Providers tab. Do not put it in an app env var, a workflow secret, a fixture, or Cursor's model settings.
- Examples contain placeholders. SQL uses `${VAR}` placeholders, never literal keys.
- If a real secret is committed, rotate it. Removing the file is not enough.
