-- Lazarus tables (Postgres / Zetaris). Same columns as app/data/seed/*.csv.
CREATE TABLE IF NOT EXISTS fields (field text PRIMARY KEY, parent_field text NOT NULL);
CREATE TABLE IF NOT EXISTS papers (
    paper_id text PRIMARY KEY, title text NOT NULL, field text REFERENCES fields(field), year int NOT NULL,
    cited_by_count int, entities text, abstract text
);
CREATE TABLE IF NOT EXISTS paper_entities (paper_id text REFERENCES papers(paper_id), entity text NOT NULL, PRIMARY KEY (paper_id, entity));
CREATE TABLE IF NOT EXISTS problems (
    problem_id text PRIMARY KEY, title text NOT NULL, field text REFERENCES fields(field), year int NOT NULL,
    statement text, key_entities text
);
CREATE TABLE IF NOT EXISTS problem_entities (problem_id text REFERENCES problems(problem_id), entity text NOT NULL, PRIMARY KEY (problem_id, entity));
CREATE TABLE IF NOT EXISTS citations (citing_id text NOT NULL, cited_id text NOT NULL, PRIMARY KEY (citing_id, cited_id));
CREATE TABLE IF NOT EXISTS entity_kinds (entity text PRIMARY KEY, kind text NOT NULL); -- method | mechanism | object | generic
CREATE INDEX IF NOT EXISTS paper_entities_entity_idx ON paper_entities (entity);
CREATE INDEX IF NOT EXISTS citations_cited_idx ON citations (cited_id);

-- Semantic view for Zetaris: candidate bridges per problem (other parent field, shared method/mechanism entities)
CREATE OR REPLACE VIEW v_candidate_bridges AS
SELECT q.problem_id, p.paper_id, p.field AS paper_field, p.year AS paper_year, q.year AS problem_year,
       COUNT(*) AS shared_method_entities
FROM problems q JOIN fields fq ON fq.field = q.field
JOIN problem_entities qe ON qe.problem_id = q.problem_id
JOIN entity_kinds k ON k.entity = qe.entity AND k.kind IN ('method','mechanism')
JOIN paper_entities pe ON pe.entity = qe.entity
JOIN papers p ON p.paper_id = pe.paper_id JOIN fields fp ON fp.field = p.field
WHERE fp.parent_field <> fq.parent_field
GROUP BY q.problem_id, p.paper_id, p.field, p.year, q.year;
