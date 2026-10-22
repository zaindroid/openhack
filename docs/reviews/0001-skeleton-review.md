# 0001. Skeleton review

- Commit reviewed: `d6372d01505776c190941b7447928f4e8ec9d420` on `main`
- Date: 2026-10-22
- Branch with fixes: `review/skeleton-fixes` (not pushed to `main`)
- Checked: every tracked file, `git check-ignore`, `make test`, `docker compose config` (Compose 2.40.3), UI `tsc --noEmit`, `vite build`, and `npm ci`

## Follow-up: Windows task runner

The owner asked whether this works on Windows, where most of the team does not have Make. The Makefile described below has been removed. The same commands are `python tasks.py <command>` (`py tasks.py <command>` on Windows): `init-env`, `check-env`, `up`, `up-all`, `down`, `config`, `zetaris-sync`, `test`, `lint`.

`tasks.py` is stdlib only. It uses `pathlib` and `subprocess` argument lists, never a shell, and the current interpreter instead of a hard-coded `python3`. `init-env` copies each missing `.env.example` to `.env` and does not overwrite. Compose is still `docker compose -p floodsense-app`, and the script also pins `--project-directory` and `-f compose.yaml`. `down` still has no `-v` and does not require `pgvector/.env`. PowerShell 5.x has no `&&`, so the README shows one command per line. In PowerShell, `curl` is an alias of `Invoke-WebRequest`; the health check is `Invoke-RestMethod`. Virtualenv binaries are `.venv\Scripts\` on Windows and `.venv/bin/` on Unix. `npm run build` still contains `&&`, which npm runs via `cmd.exe` on Windows, not via PowerShell.

Checked on Linux: `python tasks.py test` (the new task tests plus the API, agent, and sync tests), `lint`, `check-env` with nothing copied (exit 1, names the three files), and `config` with `COMPOSE_PROJECT_NAME=zetaris-stack` and a hostile `COMPOSE_FILE` (still project `floodsense-app`). `down` with no env files reaches Docker and fails here because the daemon is not running, not because `pgvector/.env` is missing. Native Windows PowerShell 5, PowerShell 7, cmd, and Docker Desktop were not executed.

The findings below are the original review. Where they say `make`, read `python tasks.py`.

Severity used below:

- **High** — can attach this stack to someone else's Compose project, or can block the only safe way to stop it.
- **Medium** — wrong setting wins silently, or a dev port is exposed beyond the laptop.
- **Low** — Day-1 footgun that does not break the happy path.
- **Info** — recorded so the next branch does not rediscover it. No code change, or a comment only.

## High

### H1. `COMPOSE_PROJECT_NAME` overrides `name: floodsense-app`

- File: `compose.yaml`, `Makefile`
- What: Compose 2.40 resolves the project name as `-p`, then `COMPOSE_PROJECT_NAME`, then the file's `name:`. `COMPOSE_PROJECT_NAME=zetaris-stack docker compose config` rendered `name: zetaris-stack` and, before the volume fix, `zetaris-stack_checkpoints`. Those containers would show up in the other project. `docker compose down --remove-orphans` from a Zetaris checkout could remove them. The network stayed `floodsense-app-net` only because that name is explicit.
- Fix applied: every Makefile Compose invocation passes `-p floodsense-app`. Re-checked: the same exported variable with `make config` stays `name: floodsense-app`. Volume names are now explicit (`floodsense-app_checkpoints`, `floodsense-app_pgdata`), so a bare `docker compose` no longer creates `zetaris-stack_*` volumes. README, `infra/README.md`, and `docs/GAMEPLAN.md` say not to run a bare `docker compose up`.
- Still true: a bare `docker compose up` while that variable is exported still joins the other project. The file's `name:` cannot win over the variable. Use `python tasks.py up` or pass `-p floodsense-app`.

### H2. `make down` could not parse when `pgvector/.env` was absent

- File: `compose.yaml`, `Makefile`
- What: the quick start treats `pgvector/.env` as optional. `make down` always passes `--profile rag --profile cache`. `docker compose --profile rag --profile cache config` exited 1 with `env file pgvector/.env not found`. The command the comments tell people to use instead of `docker system prune` failed at parse time. Default `config` (no profiles) did not require that file. Missing `api/.env` failed the same way for every command, with a Docker stat error rather than the copy command.
- Fix applied: `env_file.required: false` on api, agents, ui, and pgvector (Compose v2.24+). `make config` with both profiles now exits 0 with no env files present. `make up` still stops, before Docker, until `api/.env`, `agents/.env`, and `ui/.env` exist, and it prints the `cp` line. `make up-all` also requires `pgvector/.env`. `make down` does not.
- Not re-checked against a live engine: this VM has no Docker daemon (`docker compose down` → `unix:///var/run/docker.sock` refused). `make config` uses the same project flags and profiles as `make down`.
- Remaining: `docker compose --profile rag up` without `pgvector/.env` now parses, and Postgres will exit because `POSTGRES_PASSWORD` is unset. `make up-all` refuses that. Do not start the profile with a bare Compose command.

## Medium

### M1. `REDIS_URL` in `api/.env` was overwritten

- File: `compose.yaml`, `api/.env.example`, `.env.example`
- What: `environment: REDIS_URL: ${REDIS_URL:-}` always set the variable from the root `.env`, or to empty. That block wins over `env_file`. Checked: `REDIS_URL=redis://from-api-env` in `api/.env` rendered as empty when the root file was absent, and as the root value when the root file was set. `api/.env.example` tells people to put the cache URL there.
- Fix applied: the override is gone. Re-checked: `REDIS_URL=redis://redis:6379/0` in `api/.env` is what `docker compose config` shows. The root example points at `api/.env` and no longer defines `REDIS_URL`.
- Remaining: the API process does not read the variable yet. The footgun would have shown up with the cache client, or as soon as someone filled the file.

### M2. Published ports were on all interfaces

- File: `compose.yaml`
- What: rendered ports had no `host_ip`, so Docker publishes on `0.0.0.0`. Redis in this file has no password. `pgvector/.env.example` contains the password `local-dev-only`, which is a placeholder, and it would have been enough to log in from the LAN. The UI container is a Vite dev server (see M3).
- Fix applied: API `18000`, UI `15173`, pgvector `15432`, and Redis `16379` bind to `127.0.0.1`. Re-checked `host_ip` in `make config`. README, infra notes, the gameplan, and `pgvector/README.md` say so.
- Tradeoff: a phone on the same Wi-Fi cannot open the UI until this bind is widened. That matches the documented `curl http://127.0.0.1:18000/health` flow.
- Remaining: loopback does not stop a browser on the same machine from calling the Vite dev server.

### M3. Vite 5 and esbuild dev-server advisories

- File: `ui/package.json`, `ui/package-lock.json`
- What: `npm audit` reports vite as high for versions `<=6.4.3` and esbuild as moderate for `<=0.24.2`. The set includes path traversal in optimized-deps source maps, `server.fs.allow` / `server.fs.deny` bypasses, Windows `launch-editor` issues, and the esbuild issue where a site the developer has open can send requests to the dev server and read the response. `npm run dev` inside Compose is that dev server.
- Fix applied: none on the version. Moving off Vite 5 onto a patched 6.4 or 7 line is a major upgrade and was left for the UI owner. The loopback bind in M2 is the mitigation that landed. A lockfile is committed so the audited tree does not float, and `npm ci` exits 0 on this host.
- Recommended: bump Vite on the UI branch and run `npm audit` again. Do not run `npm audit fix --force`.

### M4. The root example used container hostnames for a host file

- File: `.env.example`, `ingestion/.env.example`, `agents/.env.example`, `zetaris/README.md`, `scripts/zetaris_sync.py`
- What: the root example set `ZETARIS_REST_URL` and `METERLESS_BASE_URL` to `host.docker.internal`. Compose does not inject the root file into containers. `make zetaris-sync` runs with host Python. That hostname usually does not resolve on the host. `ingestion/.env.example` already had `127.0.0.1`. The same keys also live in `agents/.env`. The stub loads none of them, so nothing fails today. The first real sync will, if it reads the file the quick start fills first.
- Fix applied: root defaults are `127.0.0.1`, and the comment says containers keep using `agents/.env`. The gameplan, Zetaris README, agents README, and the stub's own message name `ingestion/.env` as the host file. The stub still applies no SQL and still exits 0.
- Recommended: when the sync script is written, load `ingestion/.env` only.

## Low

### L1. The agents image did not install `requirements.txt`

- File: `agents/Dockerfile`, `agents/.dockerignore`
- What: the API image installs its requirements file. The agents image copied only the package. The file is comments, so the process runs. The next line added to that file would be missing in the container.
- Fix applied: same `pip install --no-cache-dir -r requirements.txt` as the API. A local `pip install -r agents/requirements.txt` succeeds. `tests/` is in the agents `.dockerignore`. The image was not built (no daemon).

### L2. The UI image ran `npm install` with no lockfile

- File: `ui/Dockerfile`, `ui/package-lock.json`
- What: every build could resolve a different tree inside the existing semver ranges.
- Fix applied: lockfileVersion 3 is committed. The Dockerfile runs `npm ci`. `npm ci` exited 0 here. Not rebuilt on `node:20-alpine`.
- The scaffold itself is fine: `tsc --noEmit` is clean, and `vite build` emitted the bundle (Vite 5.4.21).

### L3. `make test` warned under current FastAPI, and the install line assumed system pip

- File: `api/requirements.txt`, `api/tests/test_health.py`, `README.md`
- What: `fastapi>=0.115,<1` installed 0.159.1 and Starlette 1.9.0. Importing `TestClient` warned to install `httpx2`. The test still passed. The README said `pip install -r api/requirements.txt` with no virtualenv. This VM allowed a user-site install; a stock Debian or Ubuntu Python often will not.
- Fix applied: `httpx2>=2,<3`. `make test` is 1 API test, 3 agent tests, and 1 sync-stub test, with no warning. The README mentions a venv.
- Recommended: pin these packages when CI arrives so the five laptops do not float apart again.

### L4. The sync stub echoed argv

- File: `scripts/zetaris_sync.py`, `scripts/tests/test_stub.py`
- What: the stub printed `" ".join(args)`. A token on the command line would land in the terminal scrollback. Exiting 0 and sending no SQL is the documented contract.
- Fix applied: it prints the argument count and not the values. `scripts/tests/test_stub.py` passes a stand-in secret and asserts it is absent. `make test` runs that file.

### L5. Agent feature flags did not match the gameplan list

- File: `agents/.env.example`, `docs/GAMEPLAN.md`
- What: the gameplan lists `FF_SEMANTIC_CACHE`, `FF_CACHED_REPLAY`, `FF_EFAS`, and `FF_EXTRA_SEGMENTS`. The example omitted them. The same section says skeleton defaults are off where the behaviour does not exist, while `FF_SKEPTIC=true` and `FF_HITL=true` and both nodes still return `status: todo`. Nothing reads the flags yet.
- Fix applied: the four missing flags are `false`. `FF_SKEPTIC` and `FF_HITL` are unchanged, with a comment that they are the planned v1 defaults and the nodes are still placeholders.
- Recommended: at stand-up, either set those two to `false` until the nodes exist, or adjust the gameplan sentence. Left as a product call.

### L6. Git did not enforce LF

- File: `.gitattributes` (added), `.editorconfig`
- What: editorconfig asks for LF. Without a gitattributes file, a Windows checkout can rewrite scripts to CRLF. The skeleton itself had no CR bytes. The Makefile that this finding protected has since been removed; `tasks.py` is covered by `* text=auto eol=lf`.
- Fix applied: `* text=auto eol=lf`, with binary marks for images, archives, and raster types.

### L7. Ingestion had nowhere safe to put downloads

- File: `ingestion/.gitignore`, `ingestion/README.md`
- What: this folder is where EMS footprints and OSM extracts will land. Nothing ignored `raw/`, `data/`, zip, tiff, gpkg, or pbf. The first large download would be one `git add` away from the GitHub file limit.
- Fix applied: those paths and suffixes are ignored. `git check-ignore` matches `ingestion/raw/foo.tif`. `.env.example` is still not ignored.

### L8. A missing env file failed with a Docker path error

- File: `Makefile`, `README.md`
- What: before any copy, `docker compose config` failed with `env file /workspace/api/.env not found`. The root `.env` is not required (the ports have defaults). `pgvector/.env` is not required for `make up`. That was not obvious from the error.
- Fix applied: `make up` checks the three service files and prints `cp api/.env.example api/.env` (and the agents and UI lines). Verified with no env files present.

### L9. `API_PORT` does not change the listener

- File: `api/.env.example`, `api/Dockerfile`, `compose.yaml`
- What: `API_HOST` and `API_PORT` are not read. The image always listens on 8000. The host port is `FLOODSENSE_API_PORT`. `AGENTS_URL=http://agents:8100` is the in-network name. Port 8100 is not published, so a host-side API cannot use that URL unless `python -m floodsense_agents` is also on the host.
- Fix applied: comments in `api/.env.example` only.
- Recommended: when settings land, read the variables or delete them.

## Info

### I1. `make lint` exits 0

- File: `Makefile`
- What: it prints a TODO. A CI job that calls it would be green and would lint nothing.
- Fix: none. The gameplan leaves ruff, mypy, and `ui` `tsc` for the CI branch. Do not mark `make lint` required until that branch replaces the echo.

### I2. `make zetaris-sync` exits 0 and applies nothing

- File: `scripts/zetaris_sync.py`, `docs/GAMEPLAN.md`
- What: that is the written contract ("exits successfully and sends no SQL"). Flipping the exit code would make the gameplan wrong.
- Fix: none, other than L4 (no echoed arguments) and the message that names `ingestion/.env`.

### I3. No GitHub Actions, on purpose

- File: `infra/README.md`, `docs/GAMEPLAN.md`
- What: workflows are a later branch. This review did not add `.github/workflows`.
- Ready for that branch: `make test`, `make config` (parses with no secrets present), `npm ci`, and the gitignores. Still to add there: a real lint target, secret scanning, and a workflow that copies examples rather than logging `make config` from a filled `.env` (`config` prints resolved secrets).

### I4. No `pyproject.toml`

- File: `api/`, `agents/`
- What: tests push the package root onto `sys.path` and use `unittest`. That is enough for the skeleton.
- Recommended: one project file on the CI branch so install is not a path hack.

### I5. Images run as root and have no healthcheck

- File: `api/Dockerfile`, `agents/Dockerfile`, `ui/Dockerfile`
- What: normal for this placeholder. The API does not call the agents at startup, so a missing healthcheck does not fail `depends_on` today.
- Recommended: non-root user and a `/health` check when the images do real work.

### I6. No `LICENSE`

- File: repo root
- What: the gameplan switches the repo to public before submission.
- Recommended: choose a license in the security-review pass. None was added here.

### I7. Compose does not mount source trees

- File: `compose.yaml`, `ui/README.md`
- What: UI hot reload is `npm run dev` on the host. The container serves the files copied at build time. The UI README already says to run the dev server on the host.
- Fix: none.

### I8. No CORS middleware

- File: `api/app/main.py`, `ui/src/App.tsx`
- What: the placeholder does not fetch. The first call from `http://127.0.0.1:15173` to `http://127.0.0.1:18000` is cross-origin.
- Recommended: add `CORSMiddleware` then, limited to the UI origin. Not added now.

### I9. The same credentials are in three examples

- File: `.env.example`, `agents/.env.example`, `ingestion/.env.example`
- What: only `agents/.env` is loaded into containers. The root file is interpolation for ports, plus a catalog. `ingestion/.env` is the host copy.
- Fix: comments, not deletion, so the catalog stays. Fill `agents/.env` and `ingestion/.env`. Do not expect the root file to change a container.

### I10. Image tags float

- File: `compose.yaml`, Dockerfiles
- What: `python:3.12-slim`, `node:20-alpine`, `redis:7-alpine`, `pgvector/pgvector:pg16`.
- Recommended: digest pins if CI starts building images. Not pinned here.

### I11. The Architect is described as a peer

- File: `README.md`, `docs/GAMEPLAN.md`, `docs/README.md`
- What: all three say the Architect is one role among five peers, not a team lead. No conflicting "team lead" wording. Ownership is "who reviews this path", and `docs/OWNERSHIP.md` says the same.
- Fix: none.

### I12. Secrets and gitignore

- File: root and per-service `.gitignore`, every `.env.example`
- What: no filled `.env` is tracked. `git check-ignore` ignores `.env`, `api/.env`, `.env.production`, `ui/.env.local`, and `ingestion/.env.local`. It does not ignore `.env.example`, `api/.env.example`, `agents/.env.example`, `ui/.env.example`, `pgvector/.env.example`, or `ingestion/.env.example`. No NVIDIA provider key string is in the tree. The pgvector example password is the documented placeholder and is now only on loopback (M2).
- Fix: none beyond L7 and M2.

### I13. Isolation that was already right

- File: `compose.yaml`, `Makefile`, `infra/README.md`
- What: own project name in the file, own network `floodsense-app-net`, no `container_name`, no Zetaris service, image, or external volume, no ports 3000, 8888, 10000, or 8088, agents publish nothing, `extra_hosts: host-gateway` on the API and the agents, `make down` does not pass `-v`, rag and cache are profiles. The gameplan note on WSL is right: `host-gateway` is the host bridge address, not a process bound only to `127.0.0.1` on the host. Ayush and Urvashi still need to check that on Thursday.
- Fix: none, apart from H1 and H2.

### I14. What was executed

- `make test` passed at review time (API health, agent placeholders, sync stub). The same suite is now `python tasks.py test`, which also runs `tests/test_tasks.py`.
- `make config` passed with no env files, project name `floodsense-app`, loopback publishes, and explicit volume names. The same render is `python tasks.py config`.
- `make up` with no env files exited before Docker and named the missing file. `python tasks.py up` does the same, and `init-env` creates the copies.
- UI `tsc --noEmit`, `vite build`, and `npm ci` pass.
- `docker compose config` was run on Linux. Image builds and `down` against a running engine were not: there is no Docker daemon in this environment. Native Windows PowerShell and cmd were not executed here.
