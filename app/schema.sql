-- Maintenance Debt tables (Postgres / Zetaris). Column names match app/data/seed/*.csv so load_csv works unchanged.
CREATE TABLE IF NOT EXISTS bridges (
    structure_id text PRIMARY KEY, name text, state text, county text, lat double precision, lon double precision,
    year_built int, year_reconstructed int, design_life_years int,
    deck_rating int, superstructure_rating int, substructure_rating int,       -- NBI items 58/59/60, 0-9
    scour_critical boolean, adt int, adt_year int, last_inspection date, inspection_interval_months int,
    material text, posted_load_limit boolean, replacement_cost_usd bigint        -- cost: NBI items 94-96 or illustrative
);
CREATE TABLE IF NOT EXISTS dams (
    dam_id text PRIMARY KEY, name text, lat double precision, lon double precision, year_completed int,
    hazard_class text, condition text, last_inspection date, population_downstream int, eap_present boolean, replacement_cost_usd bigint
);
CREATE TABLE IF NOT EXISTS floods (county text, year int, events int, PRIMARY KEY (county, year));
CREATE TABLE IF NOT EXISTS traffic_growth (county text, year int, adt_index double precision, PRIMARY KEY (county, year));

CREATE OR REPLACE VIEW v_poor_bridges AS
  SELECT structure_id, name, county, lat, lon, adt, LEAST(deck_rating, superstructure_rating, substructure_rating) AS min_rating,
         deck_rating, superstructure_rating, substructure_rating, scour_critical, last_inspection
  FROM bridges WHERE LEAST(deck_rating, superstructure_rating, substructure_rating) <= 4;
CREATE OR REPLACE VIEW v_high_hazard_dams AS
  SELECT dam_id, name, lat, lon, condition, population_downstream, eap_present FROM dams WHERE hazard_class = 'high';
