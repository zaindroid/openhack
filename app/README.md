# Pre-mortem — learn from the laws that came before

**Track 03 · public good.** Before a law passes, find the laws that already tried the same thing elsewhere, read what
their ex-post evaluations documented, and tell the committee which risks showed up how often and which clause counters
each one. Evidence from analogues, not prediction. Every finding links to a report.

## Idea card
- **Problem.** Parliaments pass laws without a systematic look at how the same instrument performed in other
  jurisdictions. Audit offices document gaming, cost overruns, enforcement gaps and low take-up after the fact, and the
  next legislature repeats them.
- **Why now.** Evaluation reports are online and free (EU, national audit offices, OECD); legal texts have open APIs;
  a reasoning model can classify findings at scale. Nobody has wired these together for the drafting stage.
- **What it does.** For a draft law: finds analogues (same policy area, same instrument, ≥2 shared design features),
  counts which risk types their evaluations reported at medium/high magnitude, checks whether the draft already carries
  the mitigating clause, and proposes clauses, cost-estimate requests or a phased pilot. Never "pass / don't pass".
- **Who acts.** Committee clerks and legislative drafters; audit offices as data providers.

## How it runs on the shared engine
| whycore step | here |
|---|---|
| Scout | each draft law is a signal; score = number of analogues (SQL over `drafts` × `laws`) |
| Investigator | six risk types: gaming, cost_overrun, enforcement_gap, equity_harm, take_up_shortfall, unintended_market_effect |
| Skeptic | SUPPORT if ≥2 evaluated analogues reported the risk at medium/high and the draft lacks the countering clause; REJECT if the draft has the clause, or ≥3 evaluated analogues and none reported it; UNCERTAIN if <2 analogues were evaluated |
| Planner | "Add clause …" with eval ids and URLs as evidence; cost-estimate request; pilot/phase; or "widen the search" |
| Memory | rejections per policy_area+instrument, so a second draft in the same area runs with fewer tests |
| Explainer | Nemotron via Meterless writes the committee brief from the verdicts only |

## Data
Seed is **illustrative** (see `data/seed/README.md`). Real sources: EUR-Lex SPARQL (`data/fetch_eurlex.py`), national
legislation portals, European Commission evaluations, national audit offices, OECD (`data/fetch_evaluations.py` lists
them and prepares the extraction step). `schema.sql` creates the same tables in Postgres for Zetaris.

## Demo script (90 s)
1. Open the UI: three drafts waiting. Press **Run agent**.
2. Heat Pump Grant Act: 9 analogues in 6 jurisdictions. Gaming — supported, 3 analogues (IT 2020, FR 2020, UK 2020),
   draft has no income verification. Cost overrun — supported. Enforcement gap — rejected, nobody reported it. Hover a
   verdict: the SQL and row count appear.
3. E-scooter mandate: take-up shortfall and enforcement gap were reported by analogues but the draft already has phased
   rollout and an enforcement body → rejected as mitigated. Equity harm (accessibility) → supported.
4. Platform Worker Presumption Act: one evaluated analogue → everything uncertain; the run log shows the Skeptic's
   failure state and the Planner asks to widen the search.
5. Approve "Add clause: income verification". Run again: fewer tests (memory). Read the committee brief.

## Sponsor mapping
- **Zetaris** — one SQL across legislation tables, evaluation findings and the feature dictionary; in production the
  national sources are registered as separate Zetaris sources and federated.
- **Meterless** — every model call (brief writing, day-2 finding extraction) routed and metered; rejections mirrored to memory.
- **NVIDIA Nemotron** — Super for the committee brief and finding classification; Nano for fetch-time formatting.
- **Cursor** — build tool; sessions logged in the repo.

## Limits
- Evidence from analogues, not prediction. A risk not reported is not a risk absent.
- Finding classification from PDFs is model output and must be labelled as such and reviewed.
- Seed magnitudes and summaries are illustrative stand-ins, not quotations.

## Run
```bash
pip install -r requirements.txt
python -m whycore.evals app/evals.yaml        # 4/4
uvicorn whycore.app:app --port 8080
```
