# Agents

Purpose: the LangGraph runtime. Graph: **Watchers → Investigator → Skeptic → Exposure → Playbook → Judge → human-in-the-loop interrupt**, as planned. Agents read data only through Zetaris (`zetaris.py`, SELECT-only) and call models only through the Nightshift client (`nightshift.py`, pinned lanes).

Owner: Ayush (Nightshift client, H-MEM, World Model, memory, embeddings) and Zain (graph, HITL, Judge with Mihir).

```
watchers → investigator → skeptic ─┬─ not_supported, first time → revise → investigator → skeptic
                                   └─ → exposure → playbook → judge ─┬─ flagged, first time → playbook (repair) → judge
                                                                      └─ → hitl (interrupt) → end
```

| Node | Lane | What it does | Owner |
| --- | --- | --- | --- |
| `nodes/watchers.py` | SQL | Anomalies from `hazard_timeline` in the event window, cut at `replay_ts`; loads `provenance` | Zain, Ayush |
| `nodes/investigator.py` | deep | Hypotheses H1–H3 (rain→catchment→river→site) backed by claims; every claim cites a `query_id` (layer a) and the provenance row (layer b). Deterministic chain from aggregate queries; the model refines it from the same evidence | Zain, Ayush |
| `nodes/skeptic.py` | SQL (+deep rationale) | ≤ 3 counter-check queries per hypothesis → `supported` / `not_supported`; one revise edge back to the Investigator, which drops what was not supported | Zain, Ayush |
| `nodes/exposure.py` | SQL | `exposure_join` with `in_footprint = 1`: policies, sum insured, by segment → H4 with number claims | Ayush, Zain |
| `nodes/playbook.py` | deep | Actions for 6 / 24 / 72 h citing claim ids; `outbound` ones wait for approval. Also the one repair round when the Judge flags a claim | Ayush, Zain |
| `nodes/judge.py` | deep | Per-claim coverage, citation faithfulness, numbers match, licence, grounding → `judge[]` + `judge_summary`. Never deletes or rewrites | Zain, Mihir |
| `hitl.py` | — | `interrupt()`; approve / edit / reject; `approval{}`; outbound actions released only on approve / edit | Zain |

Contracts (gameplan v2 §5.5) are in `models.py` field for field: Evidence, Citation, Judge score, agent state (`run_id, thread_id, event_id, customer_id, replay_ts, anomalies[], hypotheses[], exposure{}, playbook[], judge[], approval{}, trace[]`), trace events. Extras (`claims[]`, `evidence{}`, `judge_summary`, `summary`) sit next to them and the UI may ignore them. The nodes use only the four contract views, so switching to live is `FF_LIVE_DATA=true` plus credentials.

## Run it

From the repo root, `python tasks.py init-env` copies `.env.example` to `.env` here when it is missing (Windows: `py tasks.py init-env`). With nothing filled in, the runtime starts on **FakeZetaris** (the four contract views as SQLite seed rows for Valencia 2024 / Ahr 2021 plus a synthetic portfolio) and **FakeNightshift** (deterministic), so the whole graph, the API and the UI work before credentials and live views exist. Fill `ZETARIS_REST_URL` / `ZETARIS_API_KEY` and `METERLESS_BASE_URL` / `METERLESS_RUNTIME_TOKEN` to go live.

```bash
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests          # 20 tests, < 1 s, no network
python3 -m floodsense_agents                   # http://127.0.0.1:8100 (compose: not published; the API proxies it)
```

```bash
curl -s -X POST 127.0.0.1:8100/runs -H 'content-type: application/json' \
  -d '{"question":"Why are our Valencia sites at risk?","event_id":"EMSR773","customer_id":"demo-insurer","replay_ts":"2024-10-29T18:00:00Z"}'
# -> status awaiting_approval, hypotheses[], claims[] with citations, exposure{}, playbook[], judge[], trace[]
curl -s 127.0.0.1:8100/runs/<id>/approval
curl -s -X POST 127.0.0.1:8100/runs/<id>/approval -H 'content-type: application/json' -d '{"action":"approve","reviewer":"zain"}'
curl -N 127.0.0.1:8100/runs/<id>/events        # SSE: one TraceEvent per node, then a status event
```

`POST /runs`, `GET /runs/past`, `GET /runs/{id}`, `GET|POST /runs/{id}/approval`, `GET /runs/{id}/citations`, `GET /runs/{id}/events`, `GET /config`, `GET /health`. Every response carries `served_from` (`live` here; `cache` / `replay` are set by the API layer) and `cached_at`.

`replay_ts` is the "now" of a replay: the Watchers and the Investigator only see rows at or before it, so the demo can step through 29 Oct 2024 hour by hour.

## Human-in-the-loop

`hitl.py` pauses with `interrupt()`; the checkpointer is **SQLite under `/data/checkpoints`** (the compose volume, `checkpoints.py`), so a paused run survives a restart of the container. Resume with `POST /runs/{id}/approval`: `approve` releases the outbound playbook actions, `edit` replaces the summary with the analyst's `edits` and releases, `reject` releases nothing. The decision lands in `approval{status, decision, edits, reviewer_note}` and in the trace. `FF_HITL=false` auto-approves and says so (`approval.status = "auto"`): dev only.

## Judge

`FF_JUDGE=true` scores every claim before the interrupt: coverage (≥ 1 citation), citation faithfulness (the cited query exists and returned rows; layer-c quote hash), numbers match (every number in the claim is in its cited rows, 2 % tolerance, sums over a column count), licence (no full text from a pointer-only source), grounding (deep lane sees only the claim and its evidence; offline fallback from the deterministic checks). A number the rows do not hold is never `supported`, whatever the model says. `score = 0.4·grounding + 0.2·coverage + 0.2·faithful + 0.2·numbers`. One repair round back to the Playbook for flagged claims; the repaired claim stays visible, marked `[repaired]`. `judge_summary.passes` = hallucination ≤ 5 %, coverage 100 %, overall ≥ `JUDGE_MIN_SCORE` (0.7, a proposal until the first eval run).

Eval set and runner: [`../evals/`](../evals/README.md).

## Hooks for the pair

- **Nightshift client** (Ayush): `nightshift.LLM.complete(lane, system, user, json=True) -> (text, model_id)`. `NightshiftClient` here sends the three headers and `enable_thinking=false`; replace or extend it, the nodes only use the protocol. `FakeNightshift` keys on the `TASK:` line of each system prompt (`prompts.py`).
- **Memory** (Ayush, `FF_HMEM`): `state.Memory.recall(request)` and `.store(run_id, request, claims, approval)`; `store` runs on approval only (`runtime.py`).
- **Views** (Urvashi, Saleeta): every SQL string lives in the node that runs it; column names follow `contracts` v1. If a real field differs, change the SQL there and the matching seed row in `zetaris.py`.

The NVIDIA provider key is not a variable in `.env`. It lives only in Nightshift's Providers tab. Calls send `Authorization: Bearer <METERLESS_RUNTIME_TOKEN>`, `meterless-app`, and `meterless-scope: user`.

Pinned model names: fast `nvidia/nemotron-3.5-lightning-30b-a3b`, deep `nvidia/nemotron-3-super-120b-a12b`. No `meterless/auto`.
