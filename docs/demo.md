# The demo fixture: one real LATE asset, fixed on camera

## Why a fixture
The real estate has no LATE asset, and that is the result to say proudly: every hop that carries long-lived data already
negotiates the hybrid post-quantum group X25519MLKEM768. That covers the Cloudflare edge for every hostname, the
tunnel to Traefik on servingz, and the hop from Cloudflare to the Traefik origin on hostinger-vps over the public internet.
SSH on all three hosts negotiates sntrup761x25519 or mlkem768x25519. Current verdicts: **8 AT RISK, 67 SAFE, 26 to
retire**.
- **AT RISK (8):** the three SSH host keys and five deploy keys. Ed25519 signatures can be forged once a
  cryptographically relevant quantum computer exists, and these keys must stay trustworthy past 2030.
- **To retire (26):** all 26 are certificates that the Certificate Transparency log still lists for zaindroid.me
  but that are expired or no longer served. They are not a quantum risk. They are certificates nobody tracked until the
  inventory listed them, and retiring them is cleanup, not migration.

To show the full loop (found → LATE → Approve → fixed → re-scanned → SAFE) the video uses one documented fixture. It is
an asset we own, measured with real handshakes; nothing is mocked:

| | |
|---|---|
| container | `lab-mosca-demo-tls` on `groundswell-net`, no host port, 64 MB, started by `demo_fixture.sh up` |
| endpoint | `openssl s_server` on :8443, RSA-2048 self-signed certificate made at start, groups `X25519:P-256` (classical only) |
| class | `contracts` (x = 10 y), kind tls (y = 1 y): x + y = 11 > 9 years to 2035 → **LATE** |
| control | :8080 `POST /apply`, bearer `DEMO_APPLY_TOKEN`, accepts only `X25519MLKEM768:X25519` or `X25519:P-256` |
| listed in | `targets.yaml` under `demo:` (scanned only by `scan_tls.py --demo`); its rows carry `DEMO FIXTURE` |

## How Approve applies it (and the guardrail)
The Planner's draft for the fixture is "Move … to hybrid TLS 1.3 key exchange X25519MLKEM768". It stays a draft until
a human clicks **Approve**. On approval whycore calls `MoscaDomain.on_approve`, which executes a change only if both
of these hold:
1. The target (host:port) is on the allow-list `APPLY_ALLOW`, or `APPLY_ENABLED=true`. `demo_fixture.sh up` builds
   the allow-list from the `demo:` entries in targets.yaml marked `apply: true`, so today it holds exactly
   `lab-mosca-demo-tls:8443`.
2. An executor exists for the action. The only one is the fixture's key-exchange change, posted to its
   token-protected control endpoint.

Every other approval is recorded as "approved, not executed" together with the apply command, for the operator to
run. An executed change becomes a `change` claim in the ledger; the Notary signs the run again, so the downloaded
attestation covers it and `verify.py` checks it.

## Recording
On servingz, from `~/apps/openhack-mosca`:

```bash
app/data/scanners/demo_fixture.sh up        # start the fixture, scan it, reload mosca_pg, publish mosca_s3
# lab-mosca needs DEMO_APPLY_URL and DEMO_APPLY_TOKEN (infra/.env, written by `up`): ~/zorc/deploy/create_lab_mosca.py
```

1. In the UI, **Ask**. The fixture appears as LATE: `x+y = 10+1 = 11 y > 9 y left to 2035`, kex `X25519`, cert RSA-2048.
2. **Approve** its first draft. The action shows `applied: lab-mosca-demo-tls:8443 now offers X25519MLKEM768:X25519`.
3. `app/data/scanners/demo_fixture.sh rescan`. The handshake now reports `Negotiated TLS1.3 group: X25519MLKEM768`.
4. **Ask** again. `already_hybrid` is supported, the harvest risk is rejected, and the asset is SAFE.

If the app cannot reach the fixture, `demo_fixture.sh apply` performs the same change by hand.

## Afterwards
```bash
app/data/scanners/demo_fixture.sh down      # container and rows removed; inventory must equal the pre-demo copy
```
Then delete `DEMO_APPLY_URL` and `DEMO_APPLY_TOKEN` from the lab-mosca Coolify env.
