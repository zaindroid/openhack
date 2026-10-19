-- Last Speakers: Postgres / Zetaris schema. Same shapes as app/data/seed/*.csv (DuckDB loads those directly).
CREATE TABLE IF NOT EXISTS languages (
    glottocode text PRIMARY KEY, name text NOT NULL, family text, country text, region text,
    lat double precision, lon double precision,
    speakers integer, speakers_year integer, median_speaker_age integer,
    endangerment text CHECK (endangerment IN ('vulnerable','definitely','severely','critically')),
    intergenerational_transmission boolean
);
CREATE TABLE IF NOT EXISTS resources (
    glottocode text REFERENCES languages(glottocode),
    kind text CHECK (kind IN ('audio_hours','video_hours','dictionary_entries','grammar_pages','text_corpus_words')),
    amount double precision, year integer, archive text, open_access boolean
);
CREATE TABLE IF NOT EXISTS access (
    glottocode text PRIMARY KEY REFERENCES languages(glottocode),
    nearest_town_km double precision, travel_days integer, permit_required boolean, community_contact boolean,
    orthography_exists boolean, active_linguist boolean
);
CREATE TABLE IF NOT EXISTS projects (
    glottocode text REFERENCES languages(glottocode), funder text, year integer,
    status text CHECK (status IN ('active','ended','planned'))
);
CREATE INDEX IF NOT EXISTS resources_glottocode_idx ON resources (glottocode);
CREATE INDEX IF NOT EXISTS projects_glottocode_idx ON projects (glottocode);

-- Semantic-layer view for Zetaris: urgency as the agent computes it (open archived recordings only)
CREATE OR REPLACE VIEW v_most_urgent AS
SELECT l.glottocode, l.name, l.country, l.region, l.lat, l.lon, l.speakers, l.median_speaker_age, l.endangerment,
       COALESCE(o.open_hours, 0) AS open_hours,
       (1.0 / GREATEST(l.speakers, 1)) * (l.median_speaker_age / 70.0) * (1 - LEAST(1.0, COALESCE(o.open_hours, 0) / 50.0)) * 1000 AS urgency
FROM languages l
LEFT JOIN (SELECT glottocode, SUM(amount) AS open_hours FROM resources
           WHERE kind IN ('audio_hours','video_hours') AND open_access AND archive IS NOT NULL AND archive <> ''
           GROUP BY glottocode) o ON o.glottocode = l.glottocode
WHERE l.speakers <= 500 OR l.endangerment IN ('severely','critically');

-- Load the seed CSVs into Postgres (psql):
-- \copy languages FROM 'app/data/seed/languages.csv' CSV HEADER
-- \copy resources FROM 'app/data/seed/resources.csv' CSV HEADER
-- \copy access    FROM 'app/data/seed/access.csv'    CSV HEADER
-- \copy projects  FROM 'app/data/seed/projects.csv'  CSV HEADER
