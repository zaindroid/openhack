# Last Speakers · documentation triage

**Question:** which endangered languages are closest to losing their last fluent speakers, what is blocking their
documentation, and where should a documentation team go first?

## Idea card
- **Problem.** Roughly 3 000 languages are endangered; many will lose their last fluent speakers within a generation.
  Funding for documentation is small and allocated by whoever applies, not by where the loss is most imminent or most
  recoverable. Recordings that exist often sit closed in drawers or on private drives.
- **Why now.** Glottolog publishes endangerment status and coordinates for every language; archives publish catalogues
  with access conditions; speaker ages are climbing fast in the critically endangered set. The data to triage exists;
  nothing joins it.
- **What the agent does.** Scores every endangered language by urgency = 1 / speakers × (median speaker age / 70) ×
  documentation deficit, where only *open, archived* recordings count. For each urgent language it proposes five competing
  blockers (no recordings · unreachable speakers · no orthography · resources unarchived · no active project), tests each
  one against the registers with a SQL query, rejects the ones the data does not support, and drafts actions for a funder:
  negotiate access, fund rapid audio documentation, deposit closed recordings in an open archive, develop an orthography,
  open a call. Drafts until a human approves. Memory keeps the rejected blockers per country so the next run is shorter.
- **Ethics.** Communities decide. This ranks where to *ask*, not what to *take*. Access and permit tests exist so the agent
  never recommends recording without a community contact.

## Data
| source | what | access | status |
|---|---|---|---|
| Glottolog | languoids, AES endangerment, coordinates | CC-BY CLDF download | `app/data/fetch_glottolog.py` |
| UNESCO World Atlas of Languages | speaker counts, vitality factors | web atlas | manual export |
| ELAR, PARADISEC, AILLA, AIATSIS | holdings, extent, access conditions | catalogues / OAI-PMH | `app/data/fetch_elar.py` (stub) |
| Ethnologue | speaker counts | paid | not used |

The bundled seed (`app/data/seed/`) is **illustrative**: invented placeholder languages with constructed figures, so no
real community is described with wrong numbers. `seed/README.md` maps every column to its real source.

## Run
```bash
pip install -r requirements.txt
python -m whycore.evals app/evals.yaml        # 4/4 on the seed
uvicorn whycore.app:app --port 8080           # UI, map, approve buttons
```
Docker: `cp infra/.env.example infra/.env && docker compose -f infra/docker-compose.yml up --build` (set `APP_NAME=last-speakers`).

## Demo script (90 s)
1. Open the UI: world map, five urgent languages. "Language A (Andes): 40 speakers, median age 72, 3 h of open recordings."
2. Press **Run agent**. Hover the signal: the SQL that found it, and the urgency formula in the props.
3. Competing blockers: *no recordings* SUPPORTED (3 h, under the 5 h floor), *unreachable* REJECTED (one travel day, no permit,
   community contact exists), *no orthography* REJECTED (orthography exists, 800 entries), *unarchived* REJECTED (everything is in
   ELAR), *no active project* SUPPORTED (zero projects). Each verdict shows its query and row count.
4. Scroll to "Language C (Sahel)": 80 hours recorded, all closed and unarchived — the agent's first action is to deposit them,
   not to record more. That is the point: cheapest recoverable hours first.
5. Approve one action. Run again: memory skipped 20 rejected hypotheses; the run is five tests instead of twenty-five.

## Sponsor mapping
- **Zetaris** — one federated query joins Glottolog, the archive catalogues and the project registers; the agent never reads a
  file directly in production (`DATA_BACKEND=zetaris`).
- **Meterless** — routes every explanation call to Nemotron and holds the run memory (rejections per country).
- **NVIDIA Nemotron** — writes the funder-facing explanation from the verdicts; it never decides a verdict.
- **Cursor** — the branch is built in Cursor sessions following `AGENTS.md`.

## Limits
- Urgency and the recoverable-hours estimate are stated heuristics (`TARGET_HOURS = 50`, 2 h per cooperating speaker per year);
  they rank, they do not measure.
- Speaker counts and ages are the weakest inputs everywhere in this field; the agent shows their year and source.
- Archive access conditions change; re-run the fetchers before acting on an "unarchived" verdict.
