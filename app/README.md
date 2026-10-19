# Kessler — air-traffic control for orbit

**Question the agent answers:** *Which objects come dangerously close in the next 7 days, why, and who should manoeuvre?*

## Idea card
- **Problem.** ~40 000 tracked objects share low Earth orbit; debris doubles each decade. Operators receive conjunction
  warnings as numbers (miss distance, probability) with no explanation and no coordination: who moves is settled by e-mail.
  One cascade (the Kessler syndrome) is the slow disaster that makes orbit unusable.
- **Why now.** Element sets for every active object are free and keyless (CelesTrak). Mega-constellations make thousands of
  close approaches a week; the bottleneck is explanation and coordination, not detection.
- **What it does.** Propagates the catalogue 7 days ahead, flags pairs below 5 km, names four competing reasons the pair is
  converging, tests each against the registry and fragmentation events with SQL, decides which party should manoeuvre and
  drafts the coordination message. Nothing is sent until a human approves.
- **Who acts tomorrow.** The operator named in the draft message; the shared watch list for pairs with no actor.

## How the four agents work here
| step | what | evidence |
|---|---|---|
| Scout | two-body + J2 propagation, 60 s coarse pass, 1 s refinement, 5 km threshold | the `objects` query + propagation parameters logged |
| Investigator | fragmentation · uncontrolled drift · constellation phasing · natural crossing | — |
| Skeptic | parent fragmentation event ≤ 3 y old within 150 km of the conjunction altitude · uncontrolled object with perigee < 400 km · same owner, Δa < 5 km, Δi < 1° · Δi > 20° and no debris | one SQL per test, rows cited |
| Planner | manoeuvrable, lighter payload moves; draft notice; re-screen at TCA − 24 h; flag the cloud if fragmentation | drafts until approved |

## Data
| source | access | status |
|---|---|---|
| CelesTrak GP element sets | free, no key, JSON | `app/data/fetch_celestrak.py` |
| UN Register of Objects Launched into Outer Space | free web index | `app/data/fetch_unoosa.py` (export + merge) |
| Space-Track SATCAT | free login | optional owner/country enrichment |
| ESA DISCOS fragmentation events | API key | optional; `fragmentation_events.csv` illustrative |

The seed catalogue is **illustrative** (see `app/data/seed/README.md`). It is built so four conjunctions occur, one per cause.

## Demo script (90 s)
1. Open the UI: 54 objects, 4 fragmentation events in the Data tabs. Press **Run agent** (about 5 s).
2. Four close approaches appear on the map. Open *EARTHVIEW-3 × DEB-2023-FRAG-07: 1.66 km*: fragmentation **supported**
   (FRAG-2023-A, 410 pieces, 2.9 years ago, 850 km), the other three causes **rejected** with the SQL that rejected them.
3. Read the draft notice to EarthView GmbH. Press **Approve** on action 1; action 3 flags the whole cloud for re-screening.
4. Press **Run agent** again: 12 of 16 tests skipped from memory (warm run), same answers.
5. Say the limits out loud: screening, not operations; two-body + J2, not SGP4; real elements via the fetcher.

## Sponsor mapping
- **Zetaris** — one federated query over the element catalogue, the ownership register and the fragmentation-event table
  (three different publishers); the agent reads nothing any other way.
- **Meterless** — every model call routed and metered; run memory (rejected causes per pair) mirrors into H-MEM.
- **NVIDIA Nemotron** — writes the operator-facing explanation and the coordination notice from the verdicts; never decides.
- **Cursor** — build log in the repo root `docs/` of the main project; this branch follows the same AGENTS.md.

## Limits (say them before a judge does)
Screening, not operations. Two-body + J2 secular rates, no drag, no covariance, no probability of collision. Real runs
propagate TLEs with the `sgp4` package (in `app/requirements.txt`) and re-screen at TCA − 24 h. Owner / manoeuvrability
come from registers, not from GP data; when unknown the Skeptic says "uncertain" rather than guessing.

## Run
```bash
pip install -r requirements.txt -r app/requirements.txt
python3 -m whycore.evals app/evals.yaml          # 5/5 on the illustrative catalogue
uvicorn whycore.app:app --port 8080              # http://localhost:8080
```
