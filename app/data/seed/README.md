# Seed data — ILLUSTRATIVE

Every row here is invented so the agent runs without a download. The region is the Pittsburgh area (Allegheny,
Washington, Westmoreland counties, PA) because it is the classic bridge county; the names, ratings, dates and costs
are not real assets. Regenerate with `python app/data/make_seed_illustrative.py`.

Replace with real data: `fetch_nbi.py` (FHWA NBI per-state file), `fetch_nid.py` (NID portal CSV), `fetch_fema_floods.py`
(OpenFEMA API). Traffic growth: your state DOT's county ADT index (no national file; keep the `traffic_growth.csv` shape).

NBI column map used by the domain: item 27 year built · 106 year reconstructed · 29/30 ADT and ADT year · 58/59/60 deck,
superstructure, substructure ratings (0-9; <= 4 poor) · 113 scour critical (codes 0-3) · 90/91 inspection date and interval ·
41 posting status · 94-96 improvement cost. Design life is not an NBI item (75 years default; 50 for pre-1960 steel).
