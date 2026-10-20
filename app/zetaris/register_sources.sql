-- Register Mosca's sources in the shared Zetaris (run once per fresh Zetaris instance):
--   python app/zetaris/zsql.py -f app/zetaris/register_sources.sql
-- ${VAR} placeholders are expanded from infra/.env. CREATE lines error with "already exists" on a re-run; that is fine.
-- 1. Mosca's own Postgres (Coolify service lab-mosca-pg, alias lab-mosca-pg on groundswell-net), database mosca.
CREATE DATASOURCE mosca_pg DESCRIBE BY "Mosca inventory, Postgres lab-mosca-pg database mosca" OPTIONS (
  jdbcdriver "org.postgresql.Driver",
  jdbcurl "jdbc:postgresql://lab-mosca-pg:5432/mosca",
  username "mosca",
  password "${MOSCA_PG_PASSWORD}",
  fetchsize "1000"
);
REGISTER DATASOURCE TABLES ("assets", "data_classes", "migration_paths", "scenarios", "v_clock") FROM mosca_pg;
-- 2. crt.sh's public certwatch database, live, through lab-mosca-crtsh (a data-less Postgres whose view zaindroid_ct
--    runs crt.sh's indexed full-text query over dblink at SELECT time). Direct JDBC to crt.sh fails: crt.sh rejects the
--    search_path startup parameter, and its only indexed path (identities() @@ tsquery) cannot be pushed down by Spark.
CREATE DATASOURCE crtsh_pg DESCRIBE BY "crt.sh certwatch, live via dblink gateway lab-mosca-crtsh, zaindroid.me only" OPTIONS (
  jdbcdriver "org.postgresql.Driver",
  jdbcurl "jdbc:postgresql://lab-mosca-crtsh:5432/crtsh",
  username "crtsh",
  password "${MOSCA_CRTSH_PASSWORD}",
  fetchsize "1000"
);
REGISTER DATASOURCE TABLES ("zaindroid_ct") FROM crtsh_pg;
