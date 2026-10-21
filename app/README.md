# Mosca — the post-quantum crypto-agility agent (with Notary)

**Question:** Which keys in our estate are already too late to migrate, why, and in what order do we fix them?

**One line:** Mosca inventories every public-key use in an estate you own, applies Mosca's inequality per asset
(data shelf-life + migration time > years to the policy anchor ⇒ already late), drafts the migration in order, lets a
human approve each step, and signs its own findings with ML-DSA (FIPS 204) — from an nRF5340 when one is plugged in.

## Why now
- NIST IR 8547 deprecates quantum-vulnerable public-key algorithms after 2030 and disallows them after 2035; the EU
  roadmap asks for high-risk systems by 2030. Data recorded today can be read once a cryptographically relevant quantum
  computer exists — so confidentiality with a long shelf-life is already a 2026 problem.
- Almost no organisation has a cryptographic inventory. Consultancies sell one for six figures. This is an open agent
  that produces it, reasons about it, and leaves a verifiable trail.

## How it works (whycore pattern)
| Stage | Mosca |
|---|---|
| Scout | inventory from `assets` (seed, or `app/data/scanners/` output): TLS/SSH handshakes, CT logs, repos, firmware, configs |
| Investigator | four competing readings per asset: `harvest_now_decrypt_later`, `forgery_after_qday`, `already_hybrid`, `dead_asset` |
| Skeptic | deterministic: x from `data_classes`, y from `migration_paths`, z from `algorithms.yaml` anchors (2030 / 2035 / 2040). support = LATE, uncertain = AT RISK, reject = SAFE/not applicable. Hybrid negotiations (X25519MLKEM768, mlkem768x25519) are recognised and rated SAFE |
| Planner | drafts per asset: hybrid TLS group, SSH `KexAlgorithms`, VPN PSK interim, ML-DSA-44 firmware signing, re-sign documents, retire dead assets, remove keys from repos. Every draft carries `apply`, `rollback`, `blast_radius`, `verify` |
| Human | approves in the UI; nothing is executed by the agent |
| Notary | run hook: SHA-256 chain over every claim, ML-DSA-65 (host) or ML-DSA-44 (nRF5340) signature; `/runs/{id}/extras/attestation`; `notary/verify.py` verifies offline |
| CBOM | run hook: CycloneDX 1.6 Cryptographic BOM with verdicts; `/runs/{id}/extras/cbom` |
| Memory | rejections per (kind, algorithm, data class) are remembered; second run is shorter (cold vs warm in evals) |

The model (Nemotron via Meterless) explains verdicts in plain language. **No cryptographic fact comes from the model**:
algorithm status, anchors and targets live in `app/algorithms.yaml`.

## The clock
The UI's first card lists every asset's **start-by year** (= anchor − shelf life − migration time). Anything before this
year is already late. That is the whole pitch in one table.

## Run
```bash
python -m whycore.evals app/evals.yaml                      # 6/6 on the illustrative estate
uvicorn whycore.app:app --port 8080                          # UI; hooks (Notary + CBOM) are on by default
python notary/verify.py <downloaded attestation.json>        # VERIFIED / FAIL
NOTARY_SERIAL=/dev/ttyACM0 uvicorn whycore.app:app           # sign on the nRF5340 instead (notary/nrf5340)
NOTARY_URL=http://<laptop-tailscale-ip>:8099 NOTARY_TOKEN=… uvicorn whycore.app:app   # board on another machine: notary/serve.py next to it
```

## Scanning your own estate (read-only)
```bash
cp app/data/scanners/targets.example.yaml app/data/scanners/targets.yaml   # ONLY hosts and files you own
python app/data/scanners/scan_tls.py      # cert key type/bits/expiry; negotiated TLS 1.3 group with openssl ≥ 3.5
python app/data/scanners/scan_ssh.py      # host-key algorithms (ssh-keyscan) and key-exchange offer (ssh -vv, no login)
python app/data/scanners/scan_ct.py       # Certificate Transparency entries for your domains (crt.sh)
python app/data/scanners/scan_repo.py     # PEM keys and JWT alg settings in your repositories
python app/data/scanners/scan_firmware.py # public-key OIDs inside your firmware images
SEED_DIR=app/data/inventory uvicorn whycore.app:app         # run on the real inventory (copy data_classes/migration_paths/scenarios.csv alongside)
```
Scanners perform ordinary handshakes and read local files; they never attempt logins or exploit anything. Scope is
whatever `targets.yaml` lists, and that list must be yours.

## Data in the seed (ILLUSTRATIVE)
A small invented estate: a hybrid-PQ edge (must be rated SAFE), a classical origin protecting contracts (LATE), SSH fleet,
ESP32/nRF firmware signing (forgery risk over device lifetime), a VPN, signed contracts, an expired certificate (dead),
datastores. Replace with scanner output for a real run; same columns.

## Sponsor mapping
- **Zetaris** — the inventory is a federation problem: handshake results, CT logs (crt.sh exposes a Postgres you can
  register as a source), SBOMs, and the data-classification table, queried as one semantic layer (`ZETARIS_PREFIX`).
- **Meterless** — routes Nano for triage of many files/handshakes and Super for explanations; H-MEM holds the estate
  between scans (the warm run); metering shows cost per asset.
- **NVIDIA Nemotron** — explains verdicts; VL reads configs and admin-console screenshots that never become tables;
  runs on a Jetson so the inventory never leaves the premises.
- **Cursor** — build log in `docs/cursor-log.md` (window only).

## Demo (3 min)
0:00 one sentence and the 2030/2035 dates · 0:25 the clock fills: the real estate is 8 AT RISK, 67 SAFE, 26 to retire,
none LATE, because every long-lived hop already negotiates X25519MLKEM768 · 0:55 the demo fixture (docs/demo.md, a real
classical-only endpoint we own) is LATE with the inequality on screen · 1:30 Approve → the hybrid group is enabled on the
fixture → re-scan shows X25519MLKEM768 → SAFE · 2:05 nRF5340 signs the attestation; `verify.py` says VERIFIED; a tampered copy FAILS · 2:40 CBOM
download · 2:50 sponsor line.

## Limits (stated on purpose)
- Anchors are policy dates, not forecasts of when a quantum computer arrives.
- PQ certificates are not yet issued by public CAs: the plan says "hybrid key exchange now, signatures as CAs ship".
- The nRF firmware is a skeleton to be built against pqm4 on the board; the software signer is the fallback and is labelled.
- Shelf-life and migration-time tables are judgement calls; they are data files so a security team can edit them.
