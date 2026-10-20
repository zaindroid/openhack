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
