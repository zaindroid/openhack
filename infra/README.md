# Infra

Purpose: notes for how we run FloodSense locally and, later, how CI reaches a Zetaris. The runnable definition of the local app is [`compose.yaml`](../compose.yaml) at the repo root, not a second compose file in this folder.

Owner: Mihir.

## Isolation

Our app is its own Compose project (`name: floodsense-app`):

- Own network, `floodsense-app-net`.
- Own volumes, explicitly named `floodsense-app_checkpoints` and `floodsense-app_pgdata`.
- No `container_name` (a fixed name would collide with someone else's stack).
- Published ports bind to `127.0.0.1`: API `18000`, UI `15173`, pgvector `15432`, Redis `16379`. Redis has no password, and the pgvector password in the example is a shared placeholder, so neither port is on the LAN.
- Zetaris stays on UI `:3000`, REST `:8888`, JDBC `:10000`. Nightshift stays on `:8088`.
- Containers reach those host services through `host.docker.internal` (`extra_hosts: host-gateway` on the API and agents) and the URLs in `agents/.env`.

`python tasks.py up` and `python tasks.py down` pass `-p floodsense-app`, `--project-directory`, and `-f compose.yaml` (on Windows, `py tasks.py up`). An exported `COMPOSE_PROJECT_NAME` overrides the compose file's `name:` and would put these containers in that other project (verified with Compose 2.40: `COMPOSE_PROJECT_NAME=zetaris-stack` renamed the project and the checkpoint volume). `-p` wins. `COMPOSE_FILE` cannot select another file while the task script is the entry point. Do not start this stack with a bare `docker compose up`.

They do not start, stop, or modify Zetaris. Do not run `docker system prune` or `docker volume prune` on a machine that also hosts Zetaris.

`down` includes the rag and cache profiles so those containers stop too. Their env files are optional at parse time (`env_file.required: false`, Compose v2.24+). A missing `pgvector/.env` must not make `down` fail and push someone toward `docker system prune`. `up-all` still asks for `pgvector/.env` before starting the profile. There is no Makefile. PowerShell 5.x has no `&&`, and the task script does not use a shell.

Optional profiles:

```powershell
py tasks.py up-all
```

```bash
python3 tasks.py up-all
```

`rag` adds pgvector. `cache` adds Redis. The engines sidecar (H-MEM and World Model, Ayush) is not in this skeleton.

## Not here yet

GitHub Actions (lint, test, secret guard, integration, release) land on a later feature branch. Do not add `.github/workflows` in the skeleton.
