-- Pre-mortem schema (Postgres; registered in Zetaris as source premortem_pg). Column names match app/data/seed/*.csv.

CREATE TABLE IF NOT EXISTS drafts (
    draft_id text PRIMARY KEY, title text NOT NULL, jurisdiction text, year int, policy_area text NOT NULL,
    instrument text NOT NULL,          -- subsidy | mandate | ban | tax | disclosure
    features text                      -- ';'-separated feature tokens (see features_dict)
);

CREATE TABLE IF NOT EXISTS laws (
    law_id text PRIMARY KEY, title text NOT NULL, jurisdiction text, year int, policy_area text NOT NULL,
    instrument text NOT NULL, features text
);

CREATE TABLE IF NOT EXISTS evaluations (
    eval_id text PRIMARY KEY, law_id text REFERENCES laws(law_id), year int, body text,
    finding_type text NOT NULL,        -- gaming | cost_overrun | enforcement_gap | equity_harm | take_up_shortfall | unintended_market_effect | none
    magnitude text,                    -- low | medium | high
    summary text, url text
);

CREATE TABLE IF NOT EXISTS features_dict (
    feature text PRIMARY KEY, meaning text, mitigates text   -- finding_type this clause counters, or empty
);

CREATE INDEX IF NOT EXISTS laws_area_instr_idx ON laws (policy_area, instrument);
CREATE INDEX IF NOT EXISTS evaluations_law_idx ON evaluations (law_id, finding_type);

-- Semantic-layer views (DuckDB and Postgres compatible)
CREATE OR REPLACE VIEW v_analogue_candidates AS
  SELECT d.draft_id, d.title AS draft, l.law_id, l.title AS law, l.jurisdiction, l.year, l.features
  FROM drafts d JOIN laws l ON l.policy_area = d.policy_area AND l.instrument = d.instrument;

CREATE OR REPLACE VIEW v_strong_findings AS
  SELECT e.law_id, l.jurisdiction, l.year, e.finding_type, e.magnitude, e.eval_id, e.url
  FROM evaluations e JOIN laws l ON l.law_id = e.law_id
  WHERE e.finding_type <> 'none' AND e.magnitude IN ('medium', 'high');
