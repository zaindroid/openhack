-- Kessler: Postgres tables for the same data the DuckDB demo reads from CSV. Register in Zetaris as source kessler_pg.
CREATE TABLE IF NOT EXISTS objects (
    object_id text PRIMARY KEY, name text NOT NULL, type text NOT NULL,          -- payload | rocket_body | debris | unknown
    owner text, country text, manoeuvrable boolean, launch_year int, parent_event text, mass_kg double precision,
    epoch timestamptz NOT NULL, a_km double precision NOT NULL, e double precision NOT NULL, inc_deg double precision NOT NULL,
    raan_deg double precision NOT NULL, argp_deg double precision NOT NULL, m0_deg double precision NOT NULL,
    perigee_km double precision, apogee_km double precision
);
CREATE TABLE IF NOT EXISTS fragmentation_events (
    event_id text PRIMARY KEY, parent_object text, date date, pieces int, altitude_km double precision, cause text
);
-- Conjunctions found by the agent (written back through Zetaris after each run)
CREATE TABLE IF NOT EXISTS conjunctions (
    id bigserial PRIMARY KEY, run_id text, object_a text, object_b text, tca timestamptz, miss_km double precision,
    rel_speed_km_s double precision, alt_km double precision, cause text, action text, created timestamptz DEFAULT now()
);
CREATE OR REPLACE VIEW v_uncontrolled_low AS
  SELECT object_id, name, type, owner, perigee_km, apogee_km FROM objects
  WHERE manoeuvrable = false AND perigee_km < 400 ORDER BY perigee_km;
CREATE OR REPLACE VIEW v_fragments AS
  SELECT o.object_id, o.name, o.parent_event, f.date AS event_date, f.pieces, f.altitude_km AS event_altitude_km
  FROM objects o JOIN fragmentation_events f ON f.event_id = o.parent_event;
