-- Advocate schema (Postgres / Zetaris). Same columns as app/data/seed/*.csv.
CREATE TABLE IF NOT EXISTS clients (client_id text PRIMARY KEY, name text NOT NULL, statute text, lat double precision, lon double precision, guardian_body text);
CREATE TABLE IF NOT EXISTS stations (station_id text PRIMARY KEY, client_id text REFERENCES clients(client_id), name text, lat double precision, lon double precision,
    kind text CHECK (kind IN ('lagoon','inflow','groundwater')));
CREATE TABLE IF NOT EXISTS measurements (station_id text REFERENCES stations(station_id), date date NOT NULL, parameter text NOT NULL, value double precision,
    PRIMARY KEY (station_id, date, parameter));
CREATE TABLE IF NOT EXISTS thresholds (parameter text PRIMARY KEY, limit_value double precision, direction text CHECK (direction IN ('above','below','none')), legal_basis text);
CREATE TABLE IF NOT EXISTS permits (permit_id text PRIMARY KEY, holder text, kind text CHECK (kind IN ('abstraction','discharge','fertiliser_plan')), volume double precision, unit text,
    distance_km double precision, status text CHECK (status IN ('active','renewal_pending','expired')), expiry date);
CREATE TABLE IF NOT EXISTS decisions (decision_id text PRIMARY KEY, title text, authority text, kind text CHECK (kind IN ('planning','permit_renewal','infrastructure')),
    distance_km double precision, submitted date, deadline date, status text CHECK (status IN ('open','closed')), summary text);
CREATE TABLE IF NOT EXISTS land_use (sector text PRIMARY KEY, hectares double precision, fertiliser_t_year double precision);

-- Semantic views registered in Zetaris
CREATE OR REPLACE VIEW v_open_decisions AS
  SELECT decision_id, title, authority, kind, distance_km, deadline, summary FROM decisions WHERE status = 'open';
CREATE OR REPLACE VIEW v_lagoon_series AS
  SELECT m.station_id, s.name, s.kind, m.parameter, m.date, m.value FROM measurements m JOIN stations s ON s.station_id = m.station_id;
CREATE OR REPLACE VIEW v_permits_near AS
  SELECT permit_id, holder, kind, volume, unit, distance_km, status, expiry FROM permits WHERE distance_km <= 10;
