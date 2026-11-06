# Sealed Signals — team README (becomes README.md at submission)

Sealed Signals lets ACAPS ask a small, trusted panel of humanitarian experts (5–10 per country) to challenge and forecast
its risk analyses in one minute, behind a mask each expert chooses. A daily doorbell watches open indicators mapped to the
risk's own triggers and fires a pulse when something shifts. Answers are sealed, opened together, aggregated with the
surprisingly-popular method and reliability weights, turned into a cited draft update the analyst accepts or rejects, and
published as a group view on a public ledger. When the risk resolves, every forecast is scored, weights update, and experts
get a private calibration report. Nothing identifying ever leaves the expert's device; nothing publishes itself.

## Run

```
pip install -r engine/requirements.txt
make seed && make dev        # API on :18000
make ui                      # frontend on :5173
make demo                    # full loop on R1043, offline
make check                   # tests, UI build, fixture validation
```

## Start here
Read `docs/sealed-signals/MASTER_PROMPT.md`, pick your lane, create `lane/<name>` from `main`.

Team: Zain Ul Haq (backend) · <name> (frontend) · <name> (research & pitch). Challenge: ACAPS Ground Truth, Hackathon for Good #8.
Synthetic experts only. ACAPS Risk Radar data under ACAPS terms of use.
