# Maintenance Debt — which asset fails first

**Problem.** Every bridge, dam and pipe has a due date. Regions know the inventory but not the order: which asset is past
its design life *and* carrying the most people *and* exposed to the thing that actually breaks it. Inspectors rate
condition; nobody joins condition, exposure, floods and traffic into a ranked repair list with the reason attached.

**Why now.** The US publishes the full National Bridge Inventory and National Inventory of Dams for free every year;
OpenFEMA publishes every flood declaration. The data to answer "what fails first, and why" already exists; it is just in
three places.

**What it does.** Scout finds assets past design life or in NBI "poor" condition (any rating ≤ 4), and dams in poor
condition or high-hazard without an emergency action plan, scored by harm = exposure (ADT or people downstream) ×
condition deficit. Investigator proposes four competing causes per asset. Skeptic tests each one with SQL against the
inventories — age vs design life, scour-critical × county floods, inspection overdue, traffic growth without posting —
and rejects what the data does not support. Planner ranks repairs (post, scour countermeasures, inspect now, EAP,
rehabilitation) and publishes the region's maintenance debt. Every verdict shows its query and row count; actions are
drafts until an engineer approves them in the UI.

**Demo (90 s).** Open the UI → Run agent. Five assets surface from forty-eight. Mon Valley Crossing: 64 years on a 50-year
design life and 57 months since inspection — age and overdue supported, scour and overload rejected with numbers → "load-rate
and post". Chartiers Creek Span: 28 years old (age rejected) but scour-critical in a county with 5 floods in 5 years →
"scour countermeasures". Turtle Creek Viaduct: fresh inspection, within design life, but county traffic up 33 % since the
count and not posted → overload is the only supported cause. Loyalhanna Ridge Dam: high hazard, 4 200 people downstream,
no emergency action plan → EAP first. Approve one action; show the run log and the remembered rejections on the second run.

**Data.** FHWA NBI (free, per state) · USACE NID (free download) · OpenFEMA declarations (free API) · state DOT traffic index ·
OpenStreetMap for exposure. The shipped seed is illustrative (see `app/data/seed/README.md`); `fetch_nbi.py`,
`fetch_nid.py`, `fetch_fema_floods.py` load the real thing.

**Sponsor mapping.** Zetaris federates the bridge inventory, dam inventory, flood declarations and traffic index as one SQL
surface (set `DATA_BACKEND=zetaris`). Meterless routes every model call and keeps the run memory (rejections remembered, warm
runs skip them). NVIDIA Nemotron writes the explanation a council engineer reads; it never decides a verdict. Built in Cursor.

**Limits.** A ranking aid for engineers: the ratings are the inspector's, not ours. Design life is a default (75 years;
50 for pre-1960 steel), not an NBI field. Replacement cost in the seed is illustrative until NBI items 94-96 are loaded.
Population downstream of dams is not in the public NID export and must come from a census/GHSL grid.

**Relation to Groundswell.** Same pattern, no satellite. This branch doubles as Groundswell's exposure layer: the
`bridges`/`dams` tables and the harm index drop into its Planner unchanged.

## Run
```bash
pip install -r requirements.txt
python -m whycore.evals app/evals.yaml     # 6/6 on the seed
uvicorn whycore.app:app --port 8080
```
`AS_OF` (default 2026-10-20) fixes "today" for ages and overdue months so the evals are deterministic.
