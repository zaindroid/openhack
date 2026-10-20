# Sponsors: what each one does in Mosca (and how to check it)

## NVIDIA Nemotron: the explainer
Nemotron writes every explanation and the run-wide brief. It never decides a verdict: verdicts come from the Skeptic's
SQL, and crypto facts come from `app/algorithms.yaml`. A useful demonstration of why: asked "what is Mosca's
inequality?" with no context, both Nemotron 3.5 models invent a wrong mathematical definition. Inside Mosca they only
see the inequality's numbers for one asset, and the prompt states the overall status.

Three routes, one switch (`MODEL_ROUTE`, see `whycore/model.py` and `infra/.env.example`): `nim` (NVIDIA API Catalog),
`meterless` (Meterless Nightshift hotspot on the laptop) and `local` (vLLM on our own GPUs over Tailscale,
`infra/models/`). Explanations record the route, host and model that answered; `MODEL_REASON_FALLBACK` keeps cloud NIM
behind a local route.

## Meterless: runtime and engines
- **Runtime (route `meterless`):** `MODEL_BASE_URL=http://<laptop-tailscale-ip>:<port>/v1`, `MODEL_API_KEY` = the
  hotspot token from Nightshift, model ids as Nightshift lists them in `GET /v1/models` (`meterless/*` routing modes).
  whycore sends `meterless-app: lab-mosca` and `meterless-scope: user` on every call.
- **Engines, from source** (`whycore/meterless/`, unmodified Apache-2.0 references pinned in `engines/NOTICE`, served
  in the app container on 127.0.0.1:8790):
  - **H-MEM**: every Skeptic rejection is mirrored as a canonical memory record with provenance (`plan_run`); recall
    falls back to H-MEM by fingerprint; the engine's append-only trust ledger records every create, read and delete.
    This is what makes the warm run shorter (evals: cold vs warm test counts).
  - **World Model**: each run observes all assets with their scan facts and verdicts; the engine reports what changed
    since the previous observation (`run.extras.world_model.changes`), e.g. a negotiated group moving to X25519MLKEM768
    after a fix.
  - **Markovian**: the run-wide brief is written in bounded chunks with carried-over state instead of one prompt that
    grows with the estate (`run.extras.brief`: chunks, estimated vs measured tokens).

## Zetaris: the data layer
Every number Mosca reasons over is read through Zetaris (`mosca_pg`), and the inventory is federated with the live
Certificate Transparency log (`crtsh_pg`). Sources, the crt.sh gateway and the federated query: `docs/zetaris.md`.

## Model routes (measured by infra/model_hello.py)

| route | role | host | model (as reported) | latency s | completion tokens | tokens/s | measured (UTC) |
|---|---|---|---|---|---|---|---|
| nim | reason | integrate.api.nvidia.com | private/nvidia/nemotron-3.5-super-120b-a12b | 2.11 | 191 | 90.7 | 2026-10-20 21:19 |
| nim | fast | integrate.api.nvidia.com | nvidia/nemotron-3.5-lightning-30b-a3b | 1.48 | 181 | 122.2 | 2026-10-20 21:19 |
| meterless | reason | (unset) | nvidia/nemotron-3.5-super-vl-120b-a12b | – | – | – | FAILED 2026-10-20 21:19: no base URL for route meterless (METERLESS_BASE_URL or METERLESS_REASON_BASE_URL |
| meterless | fast | (unset) | nvidia/nemotron-3.5-lightning-30b-a3b | – | – | – | FAILED 2026-10-20 21:19: no base URL for route meterless (METERLESS_BASE_URL or METERLESS_FAST_BASE_URL) |
