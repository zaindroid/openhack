-- Dissent: Postgres / Zetaris schema. Same columns as app/data/seed/*.csv so load_seed can COPY them in.
CREATE TABLE IF NOT EXISTS indicators (
    indicator text PRIMARY KEY, label text NOT NULL, unit_default text, tolerance_pct double precision NOT NULL,
    min_abs_gap double precision NOT NULL DEFAULT 0, weight double precision NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS definitions (
    definition_id text PRIMARY KEY, source text NOT NULL, indicator text NOT NULL REFERENCES indicators(indicator),
    definition_text text NOT NULL, base_year int, coverage_note text, revision_policy text
);
CREATE TABLE IF NOT EXISTS definition_tokens (
    definition_id text NOT NULL REFERENCES definitions(definition_id), token text NOT NULL, kind text NOT NULL, -- definition | coverage | status
    PRIMARY KEY (definition_id, token, kind)
);
CREATE TABLE IF NOT EXISTS series (
    indicator text NOT NULL REFERENCES indicators(indicator), country text NOT NULL, year int NOT NULL,
    source text NOT NULL,                     -- eurostat | worldbank | un | national
    value double precision, unit text NOT NULL, fetched date, vintage_date date NOT NULL,
    definition_id text REFERENCES definitions(definition_id),
    PRIMARY KEY (indicator, country, year, source, vintage_date)
);
-- Latest vintage per source, then the disagreements: the same query the agent runs (whycore reads it through Zetaris).
-- (Keep comments above a non-view statement: the DuckDB seed loader only executes statements that START with CREATE VIEW.)
CREATE INDEX IF NOT EXISTS series_key_idx ON series (indicator, country, year);
CREATE OR REPLACE VIEW v_latest AS
  SELECT s.* FROM series s
  JOIN (SELECT indicator, country, year, source, MAX(vintage_date) AS v FROM series GROUP BY indicator, country, year, source) m
    ON s.indicator = m.indicator AND s.country = m.country AND s.year = m.year AND s.source = m.source AND s.vintage_date = m.v;
CREATE OR REPLACE VIEW v_disagreements AS
  SELECT a.indicator, i.label, a.country, a.year, a.n_sources, a.vmax, a.vmin,
         100.0 * (a.vmax - a.vmin) / ABS(a.vmean) AS spread_pct, i.tolerance_pct, i.weight
  FROM (SELECT indicator, country, year, COUNT(*) AS n_sources, MAX(value) AS vmax, MIN(value) AS vmin, AVG(value) AS vmean
        FROM v_latest GROUP BY indicator, country, year HAVING COUNT(*) >= 2) a
  JOIN indicators i ON i.indicator = a.indicator
  WHERE 100.0 * (a.vmax - a.vmin) / ABS(a.vmean) > i.tolerance_pct AND (a.vmax - a.vmin) >= i.min_abs_gap;
