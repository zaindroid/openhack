# Lazarus — the rediscovery engine

**Branch:** `idea/lazarus` · **Track:** 02 (research agents) · **Engine:** `whycore/` (shared, see repo README)

## Idea card
- **Problem.** Most papers are never cited outside their own field. Solutions to today's open problems sit, solved, in
  other disciplines and other decades. Researchers cannot read 250 million papers; search engines rank by words and recency,
  which is exactly how a 1985 ecology result stays invisible to a 2024 epidemiologist.
- **Why now.** OpenAlex made the whole citation graph free (API and S3 snapshot). Agents can now rewrite a problem in the
  vocabulary of other fields, query the graph, and test the bridge with numbers instead of vibes.
- **What it does.** Takes an open problem → finds candidate bridge papers in *other* parent fields → the Skeptic passes a
  bridge only if (1) ≥2 shared entities are methods or mechanisms (not generic words), (2) no citation path from the
  problem's field reaches the paper within 2 hops, (3) the paper is ≥5 years older → drafts a rediscovery brief for a human
  expert. Memory remembers rejected candidates per problem, so a second run is shorter.
- **Background.** Don Swanson (1986) found that fish oil and Raynaud's syndrome were linked by two literatures that never
  cited each other ("undiscovered public knowledge"). Lazarus makes that search agentic, open and testable.
- **Honest limit.** A supported bridge is a *candidate for an expert*, never a claim of novelty or priority.

## Data
| source | what | access | status |
|---|---|---|---|
| OpenAlex | works, abstracts (inverted index), concepts, referenced_works | REST, free, `mailto` polite pool; full snapshot free on S3 | `app/data/fetch_openalex.py` written; run on a machine with internet |
| Semantic Scholar / Crossref | second opinion on citations | free (key / none) | optional |
| **Seed corpus** | 45 invented papers, 4 problems, 31 citations, 62 classified entities | `app/data/seed/*.csv` | **ILLUSTRATIVE** — regenerate with `python app/data/build_seed.py` |

Tables: `problems`, `problem_entities`, `papers`, `paper_entities`, `citations`, `fields(parent_field)`, `entity_kinds`.
`app/schema.sql` creates the same in Postgres for Zetaris, plus the view `v_candidate_bridges`.

## Run
```bash
pip install -r requirements.txt
python -m whycore.evals app/evals.yaml      # 5/5 offline, no key
uvicorn whycore.app:app --port 8080         # UI
```
With a Meterless key: `MODEL_BASE_URL`, `MODEL_API_KEY`, `METERLESS_APP=lazarus`. Through Zetaris: `DATA_BACKEND=zetaris`,
`ZETARIS_REST`, `ZETARIS_PREFIX=lazarus_pg.` after loading `app/schema.sql` and the CSVs into the registered Postgres.

## Demo script (90 s)
1. Open the UI. Question: *Which solved problems in other fields answer this open problem, and is the bridge real?*
2. Run. Signal 1: "Slip detection in contact-rich manipulation" (robotics, 2025). Four candidates appear.
3. Point at the verdicts: **S1994 seismology stick-slip precursors — SUPPORTED** (4 shared mechanisms, no citation path,
   31 years older). G2010 — rejected, robotics already cites it. P2023 — rejected, two years old is not forgotten work.
   S1998 — rejected, connected in two hops. Hover a verdict: the SQL and row count appear.
4. Scroll to "Robust segmentation under domain shift": every candidate rejected → the only action is *Widen the search*.
   The agent says "I found nothing" instead of inventing a bridge.
5. Approve "Draft rediscovery brief"; show the structured brief (problem, bridge, shared mechanisms, gap years, why uncited).
6. Run again: 13 of 16 tests skipped by memory (warm run badge).

## Sponsor mapping
- **Zetaris** — one SQL door over papers, entities, citations and problems (Postgres + the OpenAlex Parquet snapshot on S3);
  the 2-hop citation test is a federated query.
- **Meterless** — every explanation call routed through it (`meterless-app: lazarus`); run memory mirrors into H-MEM.
- **NVIDIA Nemotron** — Super for the rewrite-into-other-vocabularies step and the explanations; Nano for cheap entity tagging.
- **Cursor** — build tool; sessions logged in the repo's `docs/cursor-log.md` once the build window opens.

## What is real vs illustrative
Engine, tests, fetcher: real. Corpus: invented (see `app/data/seed/README.md`). The day-2 job is an entity extractor
that labels methods/mechanisms from real abstracts; until then `fetch_openalex.py` labels everything `object`, so the
Skeptic rejects by default rather than hallucinating bridges.
