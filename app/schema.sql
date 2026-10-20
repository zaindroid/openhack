-- Mosca inventory schema (Postgres / Zetaris). Same columns as app/data/seed/*.csv and the scanners' output.
CREATE TABLE IF NOT EXISTS assets (
    asset_id text PRIMARY KEY, name text, host text, port text, kind text NOT NULL,      -- tls|ssh|vpn|cert|firmware_sig|repo_key|doc_sig
    algorithm text, key_bits text, purpose text,                                         -- confidentiality|signature|both
    negotiated_kex text, negotiated_sig text, expires date, in_use boolean DEFAULT true,
    data_class text, traffic_gb_month double precision DEFAULT 0, source text, found_at date, note text
);
CREATE TABLE IF NOT EXISTS data_classes (data_class text PRIMARY KEY, shelf_life_years double precision NOT NULL, examples text);
CREATE TABLE IF NOT EXISTS migration_paths (kind text PRIMARY KEY, migration_years double precision NOT NULL, vendor_ready boolean, note text);
CREATE TABLE IF NOT EXISTS scenarios (scenario text PRIMARY KEY, z_year int NOT NULL, note text);

-- The clock: when migration must START for each asset under the primary anchor (2035)
CREATE OR REPLACE VIEW v_clock AS
  SELECT a.asset_id, a.name, a.kind, a.algorithm, d.shelf_life_years AS x, m.migration_years AS y,
         2035 - d.shelf_life_years - m.migration_years AS start_by_year
  FROM assets a JOIN data_classes d ON a.data_class = d.data_class JOIN migration_paths m ON a.kind = m.kind
  WHERE a.in_use;
