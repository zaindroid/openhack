-- Antibiotic Watch tables (Postgres / Zetaris). Same columns as app/data/seed/*.csv.
CREATE TABLE IF NOT EXISTS resistance (
    country text NOT NULL, pathogen text NOT NULL, antibiotic_class text NOT NULL, year int NOT NULL,
    resistant_pct double precision, n_isolates int, setting text,
    PRIMARY KEY (country, pathogen, antibiotic_class, year, setting)
);
CREATE TABLE IF NOT EXISTS consumption (
    country text NOT NULL, year int NOT NULL, antibiotic_class text NOT NULL, ddd_per_1000_per_day double precision, sector text NOT NULL,
    PRIMARY KEY (country, year, antibiotic_class, sector)
);
CREATE TABLE IF NOT EXISTS livestock_use (
    country text NOT NULL, year int NOT NULL, antibiotic_class text NOT NULL, mg_per_pcu double precision,
    PRIMARY KEY (country, year, antibiotic_class)
);
CREATE TABLE IF NOT EXISTS surveillance_changes (
    country text NOT NULL, year int NOT NULL, change text NOT NULL, note text,
    PRIMARY KEY (country, year)
);
CREATE TABLE IF NOT EXISTS travel_import (
    country text NOT NULL, year int NOT NULL, pathogen text NOT NULL, imported_share_pct double precision,
    PRIMARY KEY (country, year, pathogen)
);
CREATE TABLE IF NOT EXISTS pathogens (
    pathogen text PRIMARY KEY, zoonotic boolean NOT NULL, note text
);

-- Semantic views for Zetaris / the UI
CREATE OR REPLACE VIEW v_rising_pairs AS
SELECT r2.country, r2.pathogen, r2.antibiotic_class, r2.setting, r1.resistant_pct AS pct_start, r2.resistant_pct AS pct_end,
       r2.resistant_pct - r1.resistant_pct AS rise_points, r2.n_isolates, r1.year AS year_start, r2.year AS year_end
FROM resistance r2
JOIN resistance r1 ON r1.country = r2.country AND r1.pathogen = r2.pathogen AND r1.antibiotic_class = r2.antibiotic_class
                   AND r1.setting = r2.setting AND r1.year = r2.year - 3
WHERE r2.year = (SELECT MAX(year) FROM resistance);
