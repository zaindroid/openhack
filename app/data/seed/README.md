# Seed data — ILLUSTRATIVE

Everything in this folder is an illustrative corpus written by hand so the pipeline runs end to end without internet.
The laws are real or lightly paraphrased titles (BEG, MaPrimeRénov, Boiler Upgrade Scheme, Superbonus 110, Ley Rider,
eKFV, …); the feature tags, evaluation findings, magnitudes and summaries are **plausible stand-ins, not quotations
from the cited bodies**. The `url` column points at the publishing institution's site, not at a specific report.
Do not cite these rows as facts. Replace them before any public claim.

| file | rows | what |
|---|---|---|
| drafts.csv | 3 | the draft laws the committee is asking about |
| laws.csv | 25 | already-adopted laws in three policy areas across DE/FR/NL/UK/ES/IT/EU |
| evaluations.csv | 42 | ex-post findings per law: finding_type, magnitude, summary, url |
| features_dict.csv | 13 | the feature vocabulary and which finding each clause mitigates |

## How to populate with real data
1. `python app/data/fetch_eurlex.py --keyword building --since 2010` → EU acts skeleton (features empty).
2. National acts: export from gesetze-im-internet.de / legifrance / legislation.gov.uk with the same columns.
3. Tag `features` from the act text using the vocabulary in features_dict.csv (manual, or model-assisted and flagged).
4. `python app/data/fetch_evaluations.py --pdf-list reports.csv` → downloads the audit/evaluation PDFs and writes an
   evaluations skeleton; the extraction step (Meterless → Nemotron, JSON output, `extracted_by = model`) fills
   finding_type / magnitude / summary. A human reviews before the demo.
5. Drop the CSVs here (same column names) or load `app/schema.sql` into Postgres and register it in Zetaris.

## Designed cases (what the evals check)
- D1 Heat Pump Grant Act: 9 analogues; gaming, cost overrun and market effects documented in ≥2 analogues each and no
  countering clause in the draft → supported; enforcement gap never reported → rejected.
- D2 E-scooter mandate: take-up shortfall and enforcement gap were reported by analogues but the draft already carries
  phased_rollout and enforcement_body → rejected as mitigated; equity harm (accessibility) supported.
- D3 Platform Worker Presumption Act: only one analogue has been evaluated → every risk uncertain, the Skeptic logs the
  "could not reject" failure state and the Planner asks to widen the search.
