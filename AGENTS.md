# AGENTS.md — rules for coding agents in this repo

1. `whycore/` is shared. Change it on `main`, then merge main into idea branches. Never fork it per branch.
2. An idea branch changes only `app/` (plus its README). `app/domain.py` must expose `DOMAIN`.
3. Numbers decide: every `test()` returns support/reject/uncertain from data with the SQL attached. The model explains only.
4. ≥2 competing hypotheses per signal; the Skeptic must be able to reject at least one. "All plausible" is a logged failure.
5. Actions are drafts until approved in the UI. Never auto-execute.
6. Seed data is either a real extract (say the source and date in app/README.md) or marked "illustrative" in the file name and UI.
7. SQL must run on DuckDB and Postgres (ANSI; CAST; no vendor functions).
8. Commits: author Zain Ul Haq <zainey4@gmail.com>, imperative subject, no AI attribution lines.
9. `python -m whycore.evals app/evals.yaml` must pass before a push.
