"""whycore — the shared explain-why agent engine used by every idea branch in this repo.

Pattern (same for every domain):
    Scout finds signals → Investigator proposes ≥2 competing hypotheses → Skeptic tests each with numbers
    (support / reject / uncertain, every test carries its SQL and row count) → Planner ranks actions
    (drafts until a human approves) → Memory remembers what was rejected so the next run is shorter.

The model (Nemotron via Meterless) explains; the numbers decide. Every data read goes through one DataAccess
object that can point at Zetaris (production), Postgres (dev) or DuckDB over seed CSVs (demo / CI).
"""
__version__ = "0.1.0"
