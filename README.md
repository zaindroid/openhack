# agent-lab — one engine, ten explain-why agents

Every branch of this repo is a complete, deployable agent for one idea from the Open Agent Hackathon 2026 idea review.
They all share `whycore/`: Scout → Investigator → Skeptic (numbers decide) → Planner (drafts until a human approves) →
Memory (rejections remembered, warm runs are shorter). The model (NVIDIA Nemotron via Meterless) explains; it never decides.
Every data read goes through one door (`whycore/data.py`): Zetaris in production, Postgres in dev, DuckDB over seed CSVs for
demo and CI. Every claim carries its SQL and row count; no query ⇒ "unverified".

| branch | idea | question |
|---|---|---|
| `main` | template | pump-station outages (illustrative) — keeps the core testable |
| `idea/mosca` | **Mosca + Notary** | which keys are already too late to migrate to post-quantum crypto, in what order; ML-DSA-signed attestations, CycloneDX CBOM |
| `idea/kessler` | Kessler | which satellites are on a collision course, why, who should move |
| `idea/lazarus` | Lazarus | which solved problems in other fields answer this open problem |
| `idea/advocate` | Advocate | which decisions threaten a legal-person river, and the objection to file |
| `idea/maintenance-debt` | Maintenance Debt | which bridges and dams fail first in a region, and why |
| `idea/dissent` | Dissent | where official statistics disagree about the same fact, and which to trust |
| `idea/antibiotic-watch` | Antibiotic Watch | which drug-bug pairs are rising where, and why |
| `idea/pre-mortem` | Pre-mortem | what went wrong where a similar law already passed |
| `idea/last-speakers` | Last Speakers | which endangered languages can still be documented, first |

Groundswell and Undercurrent live in their own repos.

## Run any branch
```bash
git checkout idea/kessler
pip install -r requirements.txt            # + app/requirements.txt if present
python -m whycore.evals app/evals.yaml      # deterministic checks, no key needed
uvicorn whycore.app:app --port 8080        # UI at http://localhost:8080
# or
cp infra/.env.example infra/.env && docker compose -f infra/docker-compose.yml up --build
```
Set `MODEL_BASE_URL` + `MODEL_API_KEY` (Meterless) for real explanations; `DATA_BACKEND=zetaris` + `ZETARIS_REST` to read through Zetaris.

## Layout of a branch
```
whycore/        shared engine (do not fork per idea; fix it on main and merge)
app/domain.py   the idea: Signal / Hypothesis / test / plan, views, sources
app/data/seed/  CSVs the demo runs on (real extracts where fetched, else marked illustrative)
app/data/fetch_*.py  real fetchers for the open sources (run on a machine with internet)
app/schema.sql  Postgres/Zetaris tables + views for the same data
app/evals.yaml  cases: expected supported / rejected causes, first action, warm run
app/README.md   the idea card, data sources, demo script, sponsor mapping
```
