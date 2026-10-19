# Seed data — ILLUSTRATIVE

`objects.csv` and `fragmentation_events.csv` are constructed by `../make_illustrative_seed.py`. No object here is a real
satellite; names are invented (MeshSat, EarthView, PolarCam, NAVSTAR-DEMO, RB-…, DEB-2023-FRAG-…). The catalogue is built so
that exactly four conjunctions below 5 km occur in the 7-day window, one per cause the Skeptic tests.

Replace with real data: `python3 app/data/fetch_celestrak.py --group active --limit 400` (free, no key), then
`fetch_unoosa.py` for owners. Update `description` in `app/domain.py` from "illustrative" to the fetch date.
