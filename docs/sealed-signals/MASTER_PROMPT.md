# Sealed Signals — master prompt (team of 3)

Hackathon for Good #8 · ACAPS "Ground Truth" challenge · The Hague, 6–8 Nov 2026
**Submission: Sunday 8 Nov, 12:00 CET.** Track pitches 13:00, final 15:10.

Paste this file as the first message to your coding agent (Claude Code / Cursor) inside this repo, followed by one line:
`I am on Lane A` (backend), `Lane B` (frontend) or `Lane C` (research & pitch). Everything the agent needs is here.
The repo is the fork of the organisers' challenge repo; their files (docs/, data/, notebooks/, references/) stay untouched.

---

## 0. The idea in one paragraph (keep this text identical in README, slides and UI)

Sealed Signals lets ACAPS ask a small, trusted panel of humanitarian experts (5–10 per country) to challenge and forecast
its risk analyses in one minute, behind a mask each expert chooses. A daily "doorbell" watches open indicators mapped to the
risk's own triggers and fires a pulse when something shifts (or when an analyst, or two experts, ask). Answers are sealed,
opened together, aggregated with the surprisingly-popular method and reliability weights, turned into a cited draft update
the analyst accepts or rejects, and published as a group view on a public ledger. When the risk resolves, every forecast is
Brier-scored, weights update, and experts get a private calibration report. Nothing identifying ever leaves the expert's
device; nothing publishes itself.

Tagline: **The machine rings the doorbell, the panel answers, the analyst decides, the ledger remembers.**
Demo risk: **R1043**, escalating cross-border insecurity in eastern Chad (Sudan war). Numbers from the data: 139 risks,
57 countries, 104 resolved; High risks materialised 84 %, Medium only 47 %.

## 1. Hard rules (from the ACAPS brief; a jury will check)

1. **No real expert data.** Synthetic experts and answers only (`data/synthetic/`).
2. **Expert-controlled anonymity** per answer: `known` (to ACAPS) · `pseudonym` (to peers) · `anonymous`. Public output is
   aggregate only; never return an aggregate with fewer than **5** contributions.
3. **One minute, one card, no login** (magic link). Minutes, not sessions.
4. **No chatbot feel, no engagement metrics.** AI is analyst-side only. We show calibration and outcomes, never time-in-app.
5. **Nothing publishes itself.** Rating updates reach the ledger only through the analyst's accept / edit / reject.
6. **Use the Risk Radar data** (`data/risk-radar-export.csv`) for scoring, the proof simulation and the demo.
7. Deliverables: working prototype, 3-minute pitch, repo link + short description (README).

## 2. Branches and merging

- `main` = always runnable. Nobody commits to `main` directly.
- Lanes: `lane/backend`, `lane/frontend`, `lane/research`. Rebase on `main` before every push.
- **Merge checkpoints** (whoever is free merges, the others review in 5 minutes): Sat 13:00 · Sat 20:00 · Sun 10:30 (freeze).
- A merge must keep `make check` green (section 9). Unfinished work stays behind a flag or a stub, never breaks `main`.
- Contracts (section 4) and routes (section 5) change only by announcing in the team chat and editing this file in the same commit.
- Commits: plain messages, the human's own git identity, no AI co-author lines.

## 3. Repository layout

```
README.md                         what we built, how it works, why (Lane C writes narrative, Lane A the run instructions)
docs/sealed-signals/
  MASTER_PROMPT.md                this file
  contracts.md                    section 4 + 5 in detail, kept in sync
  demo-script.md                  3-minute script (Lane C)
  impact.md                       stakeholders, before/after, impact chain (Lane C)
  judging-checklist.md            every jury dimension → where we show it (Lane C)
fixtures/                         JSON examples of every API response — Lane B builds against these first
engine/                           Python 3.12 · FastAPI · SQLite (Lane A)
  engine/{settings,models,db,anonymity,seal,aggregate,scoring,analyst,api}.py
  engine/doorbell/{connectors.py,trigger_map.py,detect.py,run_daily.py}
  engine/sim/simulate_panels.py   backtest on the 104 resolved risks → reports/proof.json + proof.png
  tests/                          pytest, offline, < 5 s
ui/                               Lane B: Vite + React (or Lovable export committed here); .env: VITE_API_URL=http://127.0.0.1:18000
scripts/seed.py                   synthetic experts/panels/answers into the DB
scripts/demo_replay.py            replays stored indicator history for eastern Chad, fires the R1043 pulse
data/synthetic/                   experts.json, panels.json, answers.json, indicators_chad.csv (aggregated counts only)
reports/                          proof.png, proof.json
Makefile                          make dev / make check / make seed / make demo
```

## 4. Contracts (engine/models.py — everyone codes against these)

```
Mask = "known" | "pseudonym" | "anonymous"

Expert        id, country_iso, pseudonym, languages[], channel ("whatsapp"|"sms"|"email"), synthetic=true
Panel         id, country_iso, expert_ids[], k_min=5
Risk          risk_id, title, country_iso, country, probability_acaps (text: Very Low..Very High), impact_acaps (1-5),
              level ("Low"|"Medium"|"High"), status, triggers[{id,title,description}], horizon_months=6, sources[]
Pulse         id, risk_id, panel_id, fired_at, reason ("doorbell"|"analyst"|"experts"|"heartbeat"), round (1|2),
              evidence[{source, indicator, value, baseline, z, url}], question, expires_at, n_answers
Answer        id, pulse_id, mask, pseudonym|null, agree (bool), probability (0..1), panel_guess (0..1),
              missing (≤240 chars), changed_mind (bool, round 2 only), sealed_at, revealed_at|null
Seal          answer_id, commitment (sha256), sealed_at, anchor|null
RoundResult   pulse_id, n, plain_mean, weighted_probability, surprisingly_popular ("yes"|"no"), dissent_index (0..1),
              distribution[{bucket, count}], agreement_by_region[{region, n, mean}], missing_themes[{theme, count}], revealed_at
DraftUpdate   id, risk_id, pulse_id, proposed_probability (text scale), proposed_level, rationale_md,
              citations[{text, url}], status ("draft"|"accepted"|"edited"|"rejected"), decided_by, decided_at, note
LedgerEntry   risk_id, pulse_id, sealed_at, group_probability, acaps_probability, acaps_level,
              outcome (null|"materialised"|"not_materialised"), resolved_at|null, verify_hash
Score         pseudonym, risk_id, brier, resolved_at, weight_after
Calibration   pseudonym, n_resolved, mean_brier, reliability_weight, moved_before_acaps (int), note   (private)
```

Every response carries `served_from: "live"` and `generated_at`. Every aggregate carries `n`; `n < 5` is never returned.

## 5. API (port 18000; CORS for http://localhost:5173)

```
GET  /health
GET  /risks                       active risks (from the CSV) · GET /risks/{risk_id}
POST /pulses                      {risk_id, reason:"analyst", question?} → Pulse
POST /pulses/doorbell/run         run the detector once → {shifts[], pulses_fired[]}
GET  /pulses/{id}                 Pulse
GET  /e/{token}                   expert card payload: {pulse, risk, round, group_view_if_round2}
POST /e/{token}/answer            Answer → {sealed_at, commitment}
POST /pulses/{id}/reveal          → RoundResult (opens round 1, starts round 2)
GET  /pulses/{id}/result          RoundResult
POST /pulses/{id}/draft           → DraftUpdate
POST /drafts/{id}/decision        {action: accept|edit|reject, edited_probability?, note} → DraftUpdate (+ LedgerEntry on accept/edit)
GET  /ledger · GET /ledger/{risk_id} · POST /ledger/verify {verify_hash} → {valid, sealed_at, anchor}
POST /risks/{risk_id}/resolve     {outcome, resolved_at} → {scores_written, weights_updated}
GET  /me/{token}/calibration      Calibration (private)
GET  /analyst/board               {super_estimators[{pseudonym, n, mean_brier, weight}], divergence[{risk_id, panel, acaps}]}
GET  /sim/proof                   contents of reports/proof.json
GET  /events                      SSE: pulse_fired · answer_sealed · round_revealed · draft_decided · risk_resolved
```

Example payloads for every route are in `fixtures/` (Lane B starts from these; Lane A keeps them true).

## 6. Algorithms (Lane A)

- **Seal**: `commitment = sha256(canonical_json(answer) + salt)`, stored with `sealed_at` before anything else; plaintext
  encrypted at rest; values appear only in aggregates after reveal. `verify_hash` of a ledger entry = sha256 of the round's
  sorted commitments. Optional daily anchor (OpenTimestamps) behind `FF_ANCHOR`.
- **Masks**: `pseudonym = HMAC(server_key, expert_id)`. Anonymous answers carry no pseudonym and count in aggregates only.
  Membership proof: `FF_ZK=true` uses a Semaphore group per panel (JS SDK in the card); default `FF_ZK=false` uses an HMAC
  credential so the demo never blocks on circuits. Say on the slide which one is running.
- **Surprisingly popular**: compare the actual share of "yes" (will materialise within 6 months) with the mean of
  `panel_guess`; the answer whose actual share exceeds its predicted share is the SP answer.
- **Weighted aggregate**: `w = 1 / (0.1 + mean_brier)` (new expert = median weight); aggregate in log-odds; extremize ×1.3;
  back to probability. Map to ACAPS's scale: <0.2 Very Low · <0.4 Low · <0.6 Medium · <0.8 High · else Very High.
- **Scoring**: Brier = (p − outcome)². Calibration per pseudonym. `moved_before_acaps` = expert on the correct side of 0.5
  while ACAPS's rating was not.
- **k-anonymity**: any aggregate needs n ≥ 5; regional breakdowns need n ≥ 3 per region or are merged.
- **Doorbell**: parse the `Triggers` column; map each trigger to indicators by keyword table (conflict/attack/raid → acled;
  refugee/displace/influx → unhcr; escalation/tension/political → gdelt); shift if 7-day count ≥ 3× the 90-day baseline
  or z ≥ 2; max one pulse per expert per 7 days; heartbeat every 28 days. Connectors ship with cached fixtures so offline works.
- **Analyst draft**: themes from `missing` texts (keyword clustering; LLM summary if `LLM_BASE_URL` is set), top dissenting
  reasons with source URLs from the risk's own `Source`/`Rationale` fields or pulse evidence; every sentence cites.

## 7. Proof simulation (Lane A builds, Lane C uses on the slide)

On the 104 resolved risks: 8 synthetic experts per risk (3 good, 3 average, 2 noisy; signal = outcome + noise). Compare
Brier of plain mean · weighted+extremized · ACAPS rating mapped to probability (Very Low .1 · Low .3 · Medium .5 · High .7 ·
Very High .9), with bootstrap CIs, plus "share of risks where the weighted panel was on the right side earlier than ACAPS".
Output `reports/proof.json` and one bar chart `reports/proof.png`. The slide states the assumptions: a method test, not a
claim about real experts.

## 8. UI (Lane B) — three screens

1. **Expert card** `/e/:token` — phone first, looks like a message from a colleague: evidence line, risk title,
   "Still High?" toggle, probability slider with words, "What will the panel say?" slider, one text line (≤240), mask picker
   (badge / nickname / ghost), big **Seal** button, 60-s countdown, "Sealed. You'll hear how it resolves." Round 2 shows the
   anonymised distribution and a "changed my mind" toggle.
2. **Analyst desk** `/desk` — projector-friendly: live envelope tray (SSE), Reveal button, distribution chart (ACAPS line,
   panel dots, SP highlight), Chad map with agreement by region, digest with cited reasons, draft card with
   Accept / Edit / Reject, super-estimator board (pseudonyms), doorbell log with evidence.
3. **Public ledger** `/ledger` — per risk: sealed-at, group probability, ACAPS rating, outcome, **Verify** (turns green).
   No names anywhere.

White background, one accent colour, big type. Build against `fixtures/` first (a `VITE_MOCK=1` mode serving the fixtures),
switch to the live API at the Saturday 20:00 merge.

## 8a. UI / UX standard (Lane B, enforced at every merge)

Professional, minimal, modern. The jury should think "this already exists in production", not "a hackathon demo".

- **Palette**: white background, near-black text, one muted accent (deep teal or slate blue), one semantic colour each for
  good / warning / critical. No neon, no gradients as decoration, no glow, no blinking or pulsing elements, no animated
  backgrounds. Motion only to explain state (an envelope locking, a chart revealing), 150–250 ms, and off under
  `prefers-reduced-motion`.
- **No emoji anywhere**: not in UI, README, slides, commit messages or the demo. Icons are a single consistent line-icon
  set (Lucide), 1.5 px stroke, used sparingly.
- **Type**: one body face (Inter or IBM Plex Sans), one weight for headings; a fixed type scale; tabular numbers for
  probabilities and scores; running text ≤ 65 characters wide. No all-caps shouting, no decorative fonts.
- **Layout**: 8-px spacing grid, consistent card edges and padding, generous whitespace, left-aligned text; phone-first for
  the expert card (375 px), projector-first for the analyst desk (1920 px, 16:9), both without horizontal scroll.
- **Components**: shadcn/ui or plain Radix primitives; every interactive element looks interactive; visible focus states;
  real empty, loading and error states (never a blank screen); a Copy button where an export would be.
- **Content**: real risk titles, real numbers from the data, synthetic experts labelled as synthetic in a footer line. Short,
  plain labels; no marketing language inside the product.
- **Charts**: one scale, labelled axes, the ACAPS rating as a reference line, the panel as points, confidence shown as
  whiskers; chart text in the page's own type and colours.
- **Adaptable**: theme tokens in one file; the same components serve expert card, desk and ledger; works on phone, laptop
  and projector; French strings isolated in a locale file even if only English ships.
- Before each merge: screenshot the three screens at phone and desktop width and attach them to the PR.

## 8b. Integration standard (Lanes A and B, enforced at every merge)

- Every feature in section 0 is wired end to end and clickable in the demo: doorbell → pulse → card → seal → reveal →
  aggregate → draft → decision → ledger → resolve → calibration. Nothing is "shown in a slide but not in the product".
- No mocked data in the final build: `VITE_MOCK` is off from the Saturday 20:00 merge; fixtures remain only for tests.
- Each technology appears exactly where it does work, and the UI says so in one quiet line where relevant:
  sealing (commitment hash + time on the ledger), masks (the chosen mask echoed on the card), surprisingly-popular
  (highlighted on the distribution chart), reliability weights (super-estimator board), doorbell (evidence line on the
  pulse), HITL (the decision log on the draft), scoring (the calibration report). If a technology has no visible effect,
  it is cut, not described.
- Feature flags (`FF_ZK`, `FF_ANCHOR`, `LLM_BASE_URL`) default to the path that works offline; the README states which
  path the demo ran with. Never claim on stage a path that is off.
- `make demo` runs the complete loop on R1043 with the synthetic panel in under 60 seconds, from a clean clone, with no
  network. That is the smoke test before every rehearsal.

## 9. Definition of done (freeze Sunday 10:30)

- `make check` green: pytest offline, UI builds, fixtures validate against the models.
- `make seed && make dev` → full loop on R1043 with synthetic experts: doorbell → pulse → 8 sealed answers → reveal →
  draft → accept → ledger → resolve → scores → calibration.
- `reports/proof.png` on the slide with assumptions.
- README: paragraph from section 0, architecture diagram, run instructions, what is synthetic vs live, limits, team.
- Pitch rehearsed twice with the QR step (jury becomes the panel); fallback `make demo` pre-loads 8 synthetic answers.

## 10. Lanes

### Lane A — Backend (engine, data, proof)
Build sections 4–7 in `engine/`, `scripts/seed.py`, `scripts/demo_replay.py`, SSE. Order: models + db + seed → risks +
pulses + answer/seal → reveal + aggregate → draft + decision + ledger → resolve + scoring + calibration → doorbell with
fixtures → simulation + proof.png. Keep `fixtures/` true to real responses (regenerate them from the running API).
Milestones: API with seeded data Sat 10:00 · full loop Sat 18:00 · proof.png Sat 20:00 · polish Sun.

### Lane B — Frontend (three screens + demo stage)
Build section 8 in `ui/` against `fixtures/` from the first hour (`VITE_MOCK=1`), then the live API. The expert card is the
hero: test it on two real phones over the venue Wi-Fi by Saturday 18:00; QR flow for the jury. Analyst desk on a projector.
Milestones: expert card mock Sat 12:00 · desk + ledger mock Sat 16:00 · live API Sat 20:00 · stage polish Sun.

### Lane C — Research, impact, pitch (no code; docs + slides)
1. **Stakeholders** (`docs/sealed-signals/impact.md`): ACAPS analysts, field experts (local NGO staff, researchers,
   anticipatory-action practitioners), ACAPS readers (UN agencies, INGOs, donors such as ECHO/FCDO/CERF, insurers), affected
   populations. For each: how the world works today → what changes with Sealed Signals → what they get out of it → how they
   want to give their view (channel, language, time) → what would make them stop. Use the four personas in the brief
   (Jose, Emily, Pierre, Aisha).
2. **Before / after**: how ACAPS produces and updates a risk today (six-step method, analyst judgement, informal expert calls);
   after: doorbell → panel → cited draft → analyst decision → ledger → score. One diagram.
3. **Impact chain**: better probability → earlier decision → anticipatory funds released (IFRC/WFP/CERF frameworks) → aid
   pre-positioned → lower cost and mortality. Cite FAO/WFP anticipatory-action evaluations; mark every number as cited or
   illustrative. Worked example on R1043 (over a million Sudanese refugees in eastern Chad since 2023).
4. **Interview Alex (ACAPS) today**: the question list in `docs/sealed-signals/questions-for-acaps.md`; write his answers
   verbatim into impact.md and quote him in the pitch.
5. **Judging checklist** (`judging-checklist.md`): each dimension (problem understanding, expert experience, anonymity &
   trust, feasibility, data use, innovation, presentation) and the MoSCoW rows → the exact screen, number or sentence
   where we show it. Anything uncovered becomes a task for Lane A/B.
6. **Deck + demo script** (`demo-script.md`): 3 minutes, QR step, fallback; slides: problem (47 %), the loop, the demo,
   the proof chart, impact chain, pilot plan for December, team. Pitch practice Saturday 16:00.
7. **README narrative** (section 0 + why + limits), and the one-paragraph submission description.
8. **More features**: a ranked list of what to add after the hackathon (voice-first on device, machine panel member,
   hardware notary, anticipatory triggers, French/Arabic), each with the stakeholder it serves.

## 11. If you get stuck
Ask in the team chat with: what you tried, the error, what you need from the other lane. Never silently change a contract.
If a lane is blocked for more than 45 minutes, swap tasks at the next checkpoint.
