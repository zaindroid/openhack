# FloodSense EU — team gameplan

Condensed from the team gameplan v2 (22 Oct 2026) for the Open Agent Hackathon 2026, Track 02: the agent that can explain why. This file is the shared playbook. It is a working plan, not a legal opinion.

Build window: Thu 22 Oct 00:00 UTC → Tue 27 Oct 23:45 UTC (Berlin: Thu 22 Oct 02:00 CEST → Wed 28 Oct 00:45 CET). Results 6 Nov.

Targets: demo freeze `v1.0.0-rc.1` Mon 26 Oct 20:00 CET · `v1.0.0` Tue 27 Oct ~14:00 CET · submission Tue 27 Oct 21:00 CET.

## What we are building

An agent team that watches European flood and weather data and explains why a place is at risk, with a cited causal chain (rain → catchment → river → site). A Skeptic tries to disprove each link. An LLM-as-a-Judge scores grounding before a human reviews the answer. The agents tell an insurer which policies and sites are exposed and what to do in the next 6–72 hours. A human approves every outbound action.

The demo replays the Valencia floods of 29 Oct 2024 (Copernicus EMS activation EMSR773) on public data federated through Zetaris. Every number on screen links to the query, the dataset, and the original source.

Mandatory stack: Zetaris (each person runs their own local Docker Compose), Meterless Nightshift (all LLM calls, NVIDIA Nemotron lanes), at least one Meterless engine in working code (H-MEM and World Model), Cursor.

Our stack: Python and LangGraph (agents, human-in-the-loop), FastAPI, React with TSX on Vite, GitHub, docker compose for our app, optional pgvector and Redis. GitHub Actions comes later, on its own branch.

## How we want the demo to score

| Criterion | What we show |
| --- | --- |
| Impact | Insurer event-response console. Valencia replay. One business-model slide: insurers pay first; lenders, site operators, and reinsurers follow; citizens get it free. |
| Technical | Small tagged increments, contract tests, HITL tests, cache and rate limits, a C4 diagram and ADRs. |
| Innovation | Skeptic loop, Judge before the human, citations down to page and paragraph, memory of past sources (H-MEM). |
| Demo | A 3–4 minute script (Saleeta). Live when Nemotron is up. Labelled cached replay when it is not. Approval on screen. |
| Product | One screen: map, causal chain, Skeptic verdicts, Judge scores, evidence drawer, approve / edit / reject. |
| Sponsor tech | Every claim cites a Zetaris `queryId`. Every LLM call goes through Nightshift on pinned Nemotron lanes. H-MEM and World Model are load-bearing. |

Win line we hold ourselves to: grounded and cited answers, Zetaris as the only data path for agents, 100% of LLM calls through Nightshift, no outbound action without approval, and cached output always labelled.

## Team

Five peers. The Architect is one role among them, not a team lead. Scope changes are proposed by the area owner and agreed at stand-up. Pairs share a branch. Every feature has a builder and a reviewer from outside the pair. Path-level detail is in [OWNERSHIP.md](OWNERSHIP.md).

| Person | Role | Owns |
| --- | --- | --- |
| Mihir | Architect | Architecture, `docs/` and ADRs, CI/CD, security review, compose, contracts. Builds the Judge with Zain. Carries the UI until Zain finishes LangGraph and HITL. |
| Urvashi | Zetaris | Ingestion with Saleeta, every Zetaris issue, migrations and `python tasks.py zetaris-sync`, vector-search research. Then tracing and the citation pipeline with Saleeta and Mihir. |
| Saleeta | Ingestion, citations, story | EMS footprint, OSM, portfolio, seed views, citation records, both the slide deck and the demo (video and live script). |
| Ayush | Nightshift, memory | Nightshift client, pinned lanes, H-MEM, World Model, short- and long-term memory, embeddings research, semantic cache, past-runs endpoint. |
| Zain | LangGraph, HITL, Judge, UI | Graph and nodes with Ayush, `interrupt()` and the checkpointer, the Judge with Mihir, then the UI. |

Pairs: Urvashi + Saleeta (data, then citations). Ayush + Zain (graph, then memory and HITL). Zain + Mihir (Judge, then UI hand-over). Urvashi + Saleeta + Mihir (document citations, behind a flag). Saleeta + everyone (deck and demo).

UI ownership is flexible. If HITL slips, Zain stays on it and the UI stays with Mihir and whoever is free. Announce it at stand-up.

## Phases

| Phase | When | Goal | Exit |
| --- | --- | --- | --- |
| P1 Foundations | Thu 22 – Fri 23 | Skeleton, contracts, first sources, agent graph on seeded views, Day-1 research and terms checks | `v0.4.0`: Investigator + Skeptic answer a real question with citations. Core sources federated on main. |
| P2 Integrate | Sat 24 | Everyone syncs. Agents switch to live views. UI v1 on the real API. | `v0.7.0`: UI shows layer (a) and (b) citations. Integration workflow green. |
| P3 Depth | Sun 25 – Mon 26 | HITL, Judge, memory, cache, document citations, eval set, demo script. | `v1.0.0-rc.1` demo freeze, Mon 26 Oct 20:00 CET. |
| P4 Ship | Tue 27 | Test the candidate, security review, tag, record, submit. | Submission sent by 21:00 CET. |

Slots are a guide (Berlin time, AM ≈ 09:30–14:00, PM ≈ 14:30–20:00). Thursday starts mid-afternoon because the clock started at 02:00 CEST. Clocks go back on Sunday 25 Oct at 03:00 (CEST → CET).

### Thursday

- Mihir: read-through, private repo, skeleton, then CI guardrails and contracts on the next branch, C4, tag `v0.0.0` only after those checks exist.
- Urvashi: Zetaris up, vector-search research, hazard view schemas, then migrations for Open-Meteo Flood / GloFAS and a discharge view, plus the sync ledger.
- Saleeta: pick 5–10 Valencia points on EMSR773, terms check with Urvashi, seed views, stage the EMS footprint.
- Ayush: Nightshift client, `/v1/models`, pinned lanes, whether embeddings are served. First node answers on seed views.
- Zain: LangGraph skeleton with Ayush, state and citation models, `run_sql` against a fake Zetaris, graph wiring.

### Friday

- Mihir: UI concept with mock data, ADR drafts, Judge rubric with Zain, reviews, tags.
- Urvashi: rain archive, `hazard_timeline`, `exposure_join`, sync dry-run, research written up.
- Saleeta: OSM sites, synthetic portfolio, EMS footprint table, provenance rows, eval-set source list.
- Ayush: World Model entities, engines sidecar, H-MEM scaffold.
- Zain: Watchers and Investigator, then the Skeptic loop (at most 3 SQL counter-checks) toward `v0.4.0`.

### Saturday (sync day)

Everyone pulls main, runs `python tasks.py zetaris-sync` (`py tasks.py zetaris-sync` on Windows), and runs our compose stack without touching Zetaris. Urvashi runs the Zetaris desk. Agents move to live views. Saleeta wires dataset → source citations. Ayush and Zain add Exposure and Playbook, then Zain starts HITL. Mihir ships interim UI v1 (`v0.7.0`).

### Sunday and Monday

Zain finishes approve / edit / reject, builds the Judge with Mihir, then moves to the UI. Ayush adds long-term memory, short-term thread memory, the semantic cache, and a labelled replay drill. Urvashi, Saleeta, and Mihir add hierarchical document chunks and the eval set (Valencia 2024, then Ahr / NRW 2021). Monday 20:00 CET is the demo freeze. After that, only `fix/*` pull requests.

### Tuesday

Everyone tests the release candidate on their own area and one other. Mihir does the security review, tags `v1.0.0` around 14:00 CET, switches the repo to public, and submits by 21:00 CET. Saleeta records the video and finishes the deck. Ayush supplies sponsor-tech evidence. Urvashi checks licences and attributions in the UI and the README.

### Daily rhythm

- 09:30 stand-up (15 min, rotate the facilitator): blockers, today's increment, yesterday's tag.
- 14:00 optional pair check-in: contract changes are announced here.
- 19:30 merge window: green branches merge to main. Unfinished work goes in behind a feature flag. Nothing stays unmerged overnight.
- 20:00 increment demo (2 min each) and tag. Mihir creates the tag as CI/CD owner.
- After every pull of main: `python tasks.py zetaris-sync` before starting work. On Windows, `py tasks.py zetaris-sync`. One command per line. PowerShell 5.x has no `&&`.

## Increments

Thirteen product increments, a release candidate, and the release. Each merges through a pull request, is demoed at 20:00, and is tagged. Tags are immutable: `v0.MINOR.0` for an increment, `v0.MINOR.PATCH` for a fix, `v1.0.0-rc.N` for candidates. A slipped increment merges behind its flag. The tag records what actually works.

This skeleton is the folder half of `v0.0.0` only. It does not create the tag. The guardrails half (GitHub Actions, secret detection, first unit tests beyond this health check) is the next feature branch.

| Tag | Increment | Owners | Scope |
| --- | --- | --- | --- |
| v0.0.0 | Skeleton and guardrails | Mihir | README, folders, env examples, gitignores, contracts, CI that blocks a tracked `.env` and an NVIDIA key string |
| v0.1.0 | First Zetaris source and seed views | Urvashi, Saleeta | Open-Meteo Flood (GloFAS) and `floodsense.discharge_daily`, seed views, sync + verify |
| v0.2.0 | First answers via Nightshift | Ayush, Zain | One graph node, pinned lanes, `run_sql`, Evidence and Citation models |
| v0.3.0 | Core sources and provenance | Urvashi, Saleeta | Rain archive, EMS footprint, OSM sites, synthetic portfolio, hazard and exposure views, provenance |
| v0.4.0 | Investigator + Skeptic | Zain, Ayush | Watchers → Investigator → Skeptic, at most 3 rounds, World Model board |
| v0.5.0 | Live views, API, compose | Zain, Ayush, Mihir, Urvashi | `FF_LIVE_DATA`, FastAPI runs and SSE, compose on all five machines |
| v0.6.0 | Exposure and playbook | Ayush, Zain | Deterministic exposure SQL, playbook actions that cite evidence |
| v0.7.0 | UI v1 | Mihir (content: Saleeta) | Map, chain, evidence drawer with layers (a) and (b), licence badges |
| v0.8.0 | Human-in-the-loop | Zain (tests: Mihir) | `interrupt()`, SQLite checkpointer, approval API, audit log |
| v0.9.0 | Memory | Ayush (tests: Zain) | H-MEM recall and write-on-approval, trust ledger, thread memory |
| v0.10.0 | Judge before HITL | Zain, Mihir | Per-claim grounding and citation scores in the approval payload |
| v0.11.0 | Layer (c) and eval set | Urvashi, Saleeta, Mihir | Hierarchical chunks in pgvector (`FF_RAG_DOCS`), Valencia 2024 + Ahr 2021 |
| v0.12.0 | Cache, limits, replay, UI hand-over | Ayush, Mihir, Zain | Semantic cache, rate limits, past runs, labelled replay, HITL screens |
| v1.0.0-rc.1 | Demo freeze | All (tag: Mihir) | Mon 20:00. Only `fix/*` after this |
| v1.0.0 | Release | Mihir | Security review, public repo, GitHub Release, submission |

### Feature flags

Flags live in env and, later, `config/flags.yaml`. Skeleton defaults are in `agents/.env.example` and are off wherever the behaviour does not exist yet.

| Flag | v1.0 default | Purpose |
| --- | --- | --- |
| `FF_LIVE_DATA` | on | Read `floodsense.*` instead of `floodsense_seed.*` |
| `FF_SKEPTIC` | on | Skeptic loop |
| `FF_JUDGE` | on | Score claims before the approval interrupt |
| `FF_HITL` | on | Approval interrupt before any outbound action |
| `FF_HMEM` | on | Long-term memory, including sources used in past runs |
| `FF_RAG_DOCS` | on if v0.11.0 passes, else off | Layer (c) document citations |
| `FF_SEMANTIC_CACHE` | on | Similar query served from a previous good answer, labelled |
| `FF_CACHED_REPLAY` | off, on if a live service fails | Labelled replay of a recorded run |
| `FF_EFAS`, `FF_EXTRA_SEGMENTS` | off | Stretch |

## Repository layout

What is in the skeleton today:

```text
README.md
compose.yaml          # our app only
tasks.py              # up, down, zetaris-sync, test, lint. No Make.
.env.example
ingestion/            # Saleeta, Urvashi — prep and seed content
zetaris/migrations/   # Urvashi — numbered SQL
agents/               # Ayush, Zain — LangGraph package skeleton
api/                  # Zain, Ayush — FastAPI, /health only
ui/                   # Mihir, then Zain — Vite + React + TSX placeholder
infra/                # Mihir — how the local stack stays isolated
docs/                 # Mihir — this file, ownership, ADRs
scripts/zetaris_sync.py   # stub
pgvector/.env.example     # optional RAG profile
```

The gameplan v2 draft placed migrations at `ingestion/zetaris/`. This skeleton keeps prep in `ingestion/` and SQL in `zetaris/migrations/` so the sync command has one obvious directory. Later folders, not created yet: `contracts/`, `knowledge/`, `engines/` (TypeScript sidecar for H-MEM and World Model), `evals/`, `demo/`, `.github/workflows/`.

## Zetaris sync

Each of us runs Zetaris locally. Objects stay in sync because they are code.

`python tasks.py zetaris-sync` runs `scripts/zetaris_sync.py` with the same interpreter, applies pending migrations in order through each person's own `ingestion/.env` (host URL `127.0.0.1`, not `agents/.env`), records SHA-256 and time in `.zetaris-sync/ledger.json`, and runs verify queries. CI will run the same command. Nobody edits views by hand in the SQL Editor. Exploring is fine. Anything that should last becomes a migration and a pull request.

**TODO:** `scripts/zetaris_sync.py` is a stub. It exits successfully and sends no SQL.

Verify output should match on every machine. That is the definition of "in sync". Credentials stay per person. No agent creates or fetches Zetaris keys.

## Running our app

`python tasks.py up` runs `docker compose -p floodsense-app up -d --build` in this repo (Windows: `py tasks.py up`). The `-p` is required: an exported `COMPOSE_PROJECT_NAME` overrides the `name:` field and would attach this stack to another project. The task script also pins `--project-directory` and `-f compose.yaml`, so `COMPOSE_FILE` cannot select another compose file. It starts the API, the agent runtime, and the UI. pgvector and Redis start with `python tasks.py up-all` (`--profile rag` and `--profile cache`). No Make, and no `&&`, so PowerShell 5.x can run it.

The stack reaches Zetaris and Nightshift through the host, as a normal client. Inside a container, `127.0.0.1` is the container itself, so URLs use `host.docker.internal`. With Docker Engine on WSL, `host-gateway` may not reach a service bound only to `127.0.0.1`. Ayush (Nightshift) and Urvashi (Zetaris) check that on Thursday. Fallback: run the API and agents on the host, and keep UI, pgvector, and Redis in compose. The `.env` URLs make that a configuration change.

Published ports bind to `127.0.0.1`: `18000` (API), `15173` (UI), `15432` (pgvector), `16379` (Redis). Agents publish nothing. The engines sidecar is not in this compose file yet. Redis has no password. The pgvector example password is a local placeholder. Loopback is what keeps those off the LAN.

`python tasks.py down` stops our project only. It does not remove named volumes. It does not stop Zetaris. It still runs when `pgvector/.env` was never created.

## Citations

Every claim shows its sources. A claim is any sentence that states a fact, a number, or a cause. One citation record feeds the agents, the Judge, the UI, and memory. Owners: Urvashi, Saleeta, and Mihir, used by every agent and screen.

| Layer | What the user sees | When |
| --- | --- | --- |
| (a) Zetaris evidence | `queryId`, SQL, view, sample rows | Agents from v0.2.0, UI from v0.7.0 |
| (b) Original source | URL, publisher, licence, attribution, access date, from `floodsense.provenance` | Data from v0.3.0, UI from v0.7.0 |
| (c) Document passage | For example "EMS report, p.12, para 3", plus a 1–2 sentence quote | v0.11.0, behind `FF_RAG_DOCS` |

Citation record (v1 contract, column names are a proposal until Urvashi and Saleeta check the real fields):

`citation_id`, `claim_id`, `layer` (`a` \| `b` \| `c`), `source_url`, `title`, `publisher`, `accessed_at`, `licence`, `attribution`, `locator` (section, page, paragraph, lines), `quote` (1–2 sentences), `content_sha256`, `storage` (`full_text` \| `pointer`), optional `query_id`.

Evidence (layer a): `query_id`, `view`, `sql`, `rows_sample` (at most 20), `row_count`, `executed_at_utc`.

What we store depends on the licence:

| Source | What we store | How we cite |
| --- | --- | --- |
| Open-licensed (Copernicus EMS / EFAS / GloFAS, Datenlizenz Deutschland, AEMET OpenData, CC BY papers) | Full text or data, chunked, embedded in pgvector | Layers (a)–(c) with the attribution the licence asks for |
| Paywalled or copyrighted (news, closed journals) | Pointer only: URL, title, publisher, date, locator, plus a short quote. No full text | Link, 1–2 sentence quote, access date |

Documents are split on their own structure (doc → section → page → paragraph → lines), not into blind fixed-size windows. A retrieved chunk keeps that path next to its embedding. The quote is checked against the stored hash before the claim is accepted.

Vector search is open. Desk research on 22 Oct 2026 found no documented vector index in Lightning SQL for our edition. Working assumption until Urvashi's Thursday check: pgvector in the `rag` profile stores chunks and embeddings; agents query it directly; the same Postgres may be registered in Zetaris as a JDBC source so metadata still has a `queryId`. Nightshift runtime 1.4 documents no `/v1/embeddings`. Ayush confirms with `GET /v1/models`. Result goes in a later ADR.

## Data we start with

Working decision for this build:

1. Start with German state gauges.
   - Bavaria: Hochwassernachrichtendienst / Bayerisches Landesamt für Umwelt (`hnd.bayern.de`). The site showed offline during the 22 Oct 2026 check. LfU download services we saw are CC BY 4.0. Confirm the HND terms before ingesting.
   - North Rhine-Westphalia: LANUK hydrological data via Open.NRW. Checked gauge datasets were under Datenlizenz Deutschland – Zero – 2.0. Confirm per dataset.
   - Rhineland-Palatinate: Ahr gauges. Their terms are a separate check from NRW.
2. Then go EU-wide for the demo and the product path: Copernicus EMS (EMSR773 Valencia, July 2021 rapid mapping, EFAS as stretch), GloFAS discharge, AEMET and SAIH Júcar for Valencia, OpenStreetMap sites, plus a synthetic insurer portfolio that is clearly labelled synthetic.
3. Open-Meteo (Flood / GloFAS REST and the rain archive) is fine for the hackathon. The data is CC BY 4.0 and the public API is free for non-commercial use. Replace Open-Meteo before any paid product. It is not a dependency we ship in a commercial offering.

Other attribution strings to confirm and then show in the UI:

- Bavaria, pending confirmation: `Datenquelle: Bayerisches Landesamt für Umwelt, www.lfu.bayern.de`
- Cross-state portal (warnings and classes only): `Datenquelle: www.hochwasserzentralen.de, Stand: TT.MM.JJJJ hh:mm`
- Copernicus: `Generated using Copernicus Emergency Management Service information [year]`
- AEMET: `© AEMET` or `Información elaborada por la Agencia Estatal de Meteorología`
- Open-Meteo: `Weather data by Open-Meteo.com`
- OpenStreetMap: `© OpenStreetMap contributors`

## Data-use rules

Working rule, not legal advice. These are the defaults while we build. A commercial launch needs a real legal review.

| Rule | What we do |
| --- | --- |
| Attribution is not permission | We need a licence or a legal exception first, then we attribute as that licence asks |
| Open data | Datenlizenz Deutschland, CC BY 4.0, and the Copernicus terms may be used, combined, and shown, with the required attribution |
| Short quotes | A short quote that supports a point we make, with the source named (Germany: quotation right, §51 UrhG). We do not copy full articles |
| Text and data mining | We respect `robots.txt` and machine-readable TDM opt-outs (DSM Directive Art. 4, §44b UrhG) and delete mined copies when we no longer need them |
| Social platforms | We follow each platform's terms |
| Show it | The UI shows licence and attribution next to the citation. The README lists sources and licences |

Day-1 task (Saleeta and Urvashi): open the terms page of every source we ingest or cite, at least `hnd.bayern.de`, LANUK NRW, the Ahr gauges, Copernicus EMS / EFAS, AEMET, SAIH Júcar, Open-Meteo, and OSM. Record licence, attribution text, and any TDM opt-out. Sources we cannot clear stay pointer-only.

## LLM-as-a-Judge

After the Playbook node and before the human, the Judge scores each claim. It does not approve anything. The human sees the scores and remains the final judge. Owners: Zain and Mihir. Increment `v0.10.0`.

| Check | Question | How |
| --- | --- | --- |
| Coverage | Does every claim have at least one citation? | Deterministic |
| Citation faithfulness | Does the quote come from the source, and does the locator resolve? | Hash and locator, then the model checks meaning |
| Grounding | Does the evidence support the claim (`supported`, `partial`, `unsupported`)? | Deep Nemotron lane via Nightshift, seeing only the claim and its evidence |
| Numbers | Does every number match its Zetaris result? | Deterministic, with a tolerance |
| Licence | Is full text shown from a pointer-only source? | Deterministic, from the citation record |

Output per claim: `claim_id`, `grounding`, `citation_faithful`, `numbers_match`, `score` (0–1), `rationale`, `model_id`, plus an overall score. Both go into the approval payload and the UI.

An unsupported claim may get one repair round back to Playbook. Otherwise it is flagged. The Judge never silently deletes or rewrites a claim. On the eval set we compare Judge labels with human labels and report agreement. The threshold is a proposal until the first eval run.

Pinned lanes, no `meterless/auto` in the demo:

- Fast: `nvidia/nemotron-3.5-lightning-30b-a3b`
- Deep: `nvidia/nemotron-3-super-120b-a12b`

Every call goes through one Nightshift client (`METERLESS_BASE_URL`, timeout 180 s) with `Authorization: Bearer`, `meterless-app`, and `meterless-scope: user`. The model id is logged on the trace.

## Evaluation set

Two real floods. The headline number is the hallucination rate: the share of claims that their own citations do not support. Saleeta and Urvashi build the set. Zain and Mihir run the metrics before the release candidate.

| Event | Official data | News |
| --- | --- | --- |
| July 2021, NRW and the Ahr valley | LANUK NRW gauges via Open.NRW; Ahr gauges run by Rhineland-Palatinate (terms to check); DWD rain; Copernicus EMS rapid mapping | Public reporting, quoted briefly with links |
| October 2024, Valencia | AEMET, SAIH Júcar (access to verify), Copernicus EMSR773, GloFAS via Open-Meteo for the hackathon | Public reporting on the alert timeline, quoted briefly with links |

Each item has a question, the facts a good answer must contain, the allowed sources, a reference answer with citations, and human labels per claim. We propose at least 10 items per event. The exact count is Saleeta and Urvashi's.

Proposed targets, for the team to confirm:

| Metric | Definition | Proposal |
| --- | --- | --- |
| Citation coverage | Claims with at least one citation / all claims | 100% |
| Citation support | Citations that support their claim / all citations | ≥ 90% |
| Quote fidelity | Quotes whose hash and locator match / all quotes | 100% |
| Numeric accuracy | Numbers equal to their Zetaris result / all numbers | 100% |
| Hallucination rate | Claims not supported by their citations / all claims | ≤ 5%, reported per release |
| Judge–human agreement | Claims where the labels agree / all labelled claims | Reported; sets the Judge threshold |

## Caching and the honest demo

Live calls are slow and can fail during the demo. The API grows three behaviours, pitched as scale and cost engineering: many analysts ask about the same event.

| Feature | Behaviour | Owner |
| --- | --- | --- |
| Semantic cache | A previous successful answer for the same or a very similar query (event, customer, replay time, flags). Only answers that finished and passed the Judge are cached. TTL is shorter for live data than for historical replays. | Ayush |
| Clear labelling | Every response carries `served_from` of `live`, `cache`, or `replay`, and `cached_at` when it is not live. The UI shows a banner such as `cached at HH:MM` (for example "Cached answer from 14:32 · not live · original run R-123"). | Ayush (API), Zain (UI) |
| Rate limiting | Per-client HTTP 429 with `Retry-After`, plus a global cap on concurrent Nightshift calls. | Mihir |
| Past runs | `GET /runs/past` lists earlier runs. Replaying one is labelled replay. | Ayush |

Live first: the demo runs live when the pinned lanes answer `GET /v1/models`. If Nightshift or Zetaris fails, the console switches to the recorded run and shows the replay banner. Saleeta's script has both paths, and she says which one is playing.

Cached or replayed output is always labelled `cached at HH:MM`. It is never presented as live. Not in the UI, not in the video, not in the deck. The trace keeps the original run's timestamps.

## Branching and tags

`main` is the integration branch. Short-lived branches (`feat/<area>-<topic>`, `fix/…`, `chore/…`) merge through a pull request with green checks and one review from outside the pair. This skeleton is the base content on `main`. From here, product work goes through those pull requests. Pairs share a branch, rebase before push, and delete the branch after merge.

Merge at least daily, at the 19:30 window. Mihir tags a green `main`. Tags are never moved or deleted. A fix gets a new tag. From `v1.0.0-rc.1` (Mon 20:00 CET) only `fix/*` pull requests land. Patches become `rc.2`, `rc.3`, and so on.

The repo stays private during the build and switches to public before submission, after the security review. On GitHub Free, rulesets and enforced code owners apply once the repo is public. Until then the team rules above are the protection, together with the CI guard that lands on the next branch.

## Secrets

- Filled env files stay untracked. Commit `.env.example` only.
- Each person creates their own Zetaris API key and their own Nightshift runtime token.
- The NVIDIA provider key lives only in Nightshift's Providers tab. It is not an application env var, a GitHub secret, a test fixture, or a Cursor model setting.
- SQL, logs, screenshots, and prompts do not contain tokens. Placeholders in examples are empty or obvious stand-ins.
- If a secret is committed, rotate it. Deleting the file is not enough.
- CI on the next branch will reject a tracked `.env` and an NVIDIA key string. That workflow is not in this commit.

## Open points and proposals

Not verified yet. Owners in parentheses.

- Zetaris vector features in our edition, pgvector registration from the Zetaris containers, vector column mapping, and pushdown (Urvashi, Thu).
- Whether Nightshift serves embeddings, and which model we use if it does not (Ayush with Urvashi).
- Container access to host services under WSL for Zetaris `:8888` and Nightshift `:8088` (Ayush, Urvashi).
- Terms of every source, especially `hnd.bayern.de` (offline during the check), the Ahr gauges, SAIH Júcar, and Open-Meteo for commercial use (Saleeta, Urvashi). Open-Meteo is accepted for the hackathon and is to be replaced before a paid product.
- Lightning SQL support for `IF NOT EXISTS`, `CREATE OR REPLACE`, and `DROP` on our object types (Urvashi).
- Python path for the Meterless engines, or a TypeScript sidecar (Ayush).
- Cursor plan features and cost for Bugbot and cloud agents (Mihir).
- Whether the repository owner has GitHub Pro. Not assumed. Rulesets while private are not part of the plan.
- View column names in the contracts section are a proposal until checked against the real source fields (Urvashi, Saleeta).
- Eval targets and the Judge threshold are proposals until the first eval run (Zain, Mihir).
- The data-use section is a working rule, not legal advice.
- Where seed rows live (small Postgres or object storage). Zetaris cannot read files on a laptop. Saleeta decides on Day 1.

## Definition of done (every later pull request)

- An acceptance test exists and the checks are green.
- The change stays in owned folders, or the owners reviewed it. Contract changes were announced.
- One review from outside the pair.
- No secrets in code, tests, fixtures, logs, or screenshots.
- New Zetaris objects arrive as a new migration plus a verify query.
- Every new claim carries a citation record. Every LLM call goes through the Nightshift client.
- Unfinished behaviour sits behind a flag. Cached output is labelled.
- README or docs updated when setup changed.

## Left as TODO in this skeleton

- `scripts/zetaris_sync.py` applies nothing.
- No SQL migrations yet.
- LangGraph graph, Nightshift client, HITL checkpointer, and Judge are placeholders.
- The API implements `/health` only.
- The UI is a Vite placeholder, not the console.
- No `engines/` sidecar, no `contracts/`, no eval items, no demo script.
- No GitHub Actions, no pre-commit hook, no enforced CODEOWNERS file.
- `python tasks.py lint` prints a TODO.
