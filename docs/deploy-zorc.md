# Deploying every branch on servingz (Coolify + Cloudflare Tunnel)

One repo, nine deployable branches, one Dockerfile. Each branch becomes its own Coolify application:

| branch | service name | hostname | host port |
|---|---|---|---|
| idea/kessler | lab-kessler | kessler.zaindroid.me | 8101 |
| idea/lazarus | lab-lazarus | lazarus.zaindroid.me | 8102 |
| idea/advocate | lab-advocate | advocate.zaindroid.me | 8103 |
| idea/maintenance-debt | lab-maintenance-debt | debt.zaindroid.me | 8104 |
| idea/dissent | lab-dissent | dissent.zaindroid.me | 8105 |
| idea/antibiotic-watch | lab-antibiotic-watch | abx.zaindroid.me | 8106 |
| idea/pre-mortem | lab-pre-mortem | premortem.zaindroid.me | 8107 |
| idea/last-speakers | lab-last-speakers | speakers.zaindroid.me | 8108 |
| main | lab-template | lab.zaindroid.me | 8100 |

## Coolify (per service)
1. New resource → Application → Git repository `https://github.com/zaindroid/agent-lab` → branch as above → build pack **Dockerfile** (root `Dockerfile`), port 8080.
2. Environment (minimum): `APP_NAME=<service>`, `METERLESS_APP=<service>`, `DATA_BACKEND=duckdb`, `MEMORY_DIR=/srv/data/memory`.
   Optional: `MODEL_BASE_URL` + `MODEL_API_KEY` (Meterless) for real explanations; `DATA_BACKEND=zetaris`, `ZETARIS_REST=http://zetaris:8888/api/v1.0`, `ZETARIS_USER`, `ZETARIS_PASSWORD`, `ZETARIS_PREFIX=<source>.` once the branch's `app/schema.sql` tables are loaded and registered in the shared Zetaris (see `docs/zetaris.md` on each branch's README).
3. Persistent volume `/srv/data/memory` (memory survives redeploys; wipe it to demo a cold run).
4. Network: join `groundswell-net` only if the service must reach the shared Zetaris; container names are `lab-*` so nothing clashes with `postgres`/`zetaris-metastore`.
5. Health check: `GET /healthz`.

## Cloudflare Tunnel
Add one public hostname per service in the zorc tunnel config → `http://lab-<name>:8080`; put all `*.zaindroid.me` lab hosts behind the existing Cloudflare Access policy.

## Without Coolify (plain compose)
```bash
git clone https://github.com/zaindroid/agent-lab && cd agent-lab && git checkout idea/kessler
cp infra/.env.example infra/.env   # set APP_NAME, APP_PORT, keys
docker compose -f infra/docker-compose.yml up -d --build
```

## Loading a branch's data into the shared Zetaris (optional, for the sponsor path)
1. `psql $DATABASE_URL -f app/schema.sql` on a per-branch database (one DB per idea; no shared `postgres` container name).
2. `python -m app.data.load_seed` where present, or `\copy` each `app/data/seed/*.csv`.
3. Register the database in Zetaris as source `<idea>_pg`; set `ZETARIS_PREFIX=<idea>_pg.` and `DATA_BACKEND=zetaris`.
