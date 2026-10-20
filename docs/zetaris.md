# Mosca on Zetaris

Mosca reads its inventory only through the shared Zetaris (hackathon bundle 2.4.3.1 on servingz, `zetaris-api-1:8888`
on `groundswell-net`). Deployed app: `DATA_BACKEND=zetaris` and `ZETARIS_TABLES=assets=mosca_s3.assets,
probes=mosca_s3.probes,data_classes=mosca_pg.data_classes,migration_paths=mosca_pg.migration_paths,scenarios=mosca_pg.scenarios`:
scan evidence comes from object storage, the editable reference tables from Postgres, joined in each statement (the
hackathon rule: Zetaris reads files from S3/APIs, not from local disk). whycore logs in with
`GET /api/v1.0/auth/login` (Basic → JWT) and runs every statement with `POST /api/v1.0/sql-editor/sqls/run`
(Bearer, `X-Org-ID`). Lightning returns every value as a string; whycore types booleans and plain numbers.

## Sources

| Zetaris source | What | Where |
|---|---|---|
| `mosca_s3` | scan evidence as Parquet on the shared MinIO, bucket `mosca`: `assets` and `probes` (current scan), `assets_history` (one `scan_date` partition per scan) | written by `app/data/scanners/publish_s3.py` (source CSV sha256 in each object's metadata); per-bucket S3A block `app/zetaris/spark-defaults.mosca.conf`, alias `mosca.minio` = `lab-mosca-s3-alias`; own MinIO user `mosca` limited to the bucket |
| `mosca_pg` | the editable reference tables the app reads: `data_classes`, `migration_paths`, `scenarios` (plus a Postgres copy of `assets` and the `v_clock` view) | Postgres `lab-mosca-pg:5432/mosca` (Coolify service `lab-mosca-pg`), loaded from `app/data/inventory/*.csv` with `app/schema.sql` |
| `crtsh_pg` | `zaindroid_ct`: every certificate crt.sh has logged for zaindroid.me (id, serial, not_after, key algorithm and size, CN, issuer), **live** | `lab-mosca-crtsh:5432/crtsh`, a Postgres with no data: its view runs crt.sh's own indexed query over `dblink` at SELECT time |

Registration: `python app/zetaris/zsql.py -f app/zetaris/register_sources.sql` (`${VAR}` from `infra/.env`).

### Why crt.sh needs a gateway
Registering `guest@crt.sh:5432/certwatch` directly as a JDBC source does not work, for two reasons found on 2026-10-20:
1. crt.sh rejects the JDBC startup parameter Lightning sends: `PSQLException: ERROR: unsupported startup parameter: search_path`.
2. Even past that (tested through PgBouncer with `ignore_startup_parameters = search_path`), the only fast path into
   crt.sh is its full-text predicate `plainto_tsquery('certwatch', 'zaindroid.me') @@ identities(certificate)`. Spark can
   push down `name_value = 'zaindroid.me'`, but crt.sh plans that as a sequential scan over ~25 billion certificate rows
   (`EXPLAIN` on `certificate_and_identities`) and cancels it at its 70 s statement timeout.

The gateway keeps the data live and at crt.sh: each `SELECT` on `crtsh_pg.zaindroid_ct` sends the indexed query to
crt.sh (≈ 5–8 s). Nothing is cached or copied.

## Verified SELECTs through the REST endpoint (2026-10-20)

| SQL | Result |
|---|---|
| `SHOW DATASOURCE TABLES mosca_pg` | assets, data_classes, migration_paths, scenarios, v_clock |
| `SELECT source, count(*) AS n FROM mosca_pg.assets GROUP BY source ORDER BY source` | ct_log 38 · repo_scan 5 · ssh_scan 3 · tls_scan 48 (434 ms) |
| the `clock` view of `app/domain.py` (prefixed) | 68 in-use assets: HYBRID KEX 48 · SAFE 12 · AT RISK 8 |
| `SELECT count(*) FROM crtsh_pg.zaindroid_ct` | 49 entries (38 serials; precertificate and certificate share one), 16 unexpired |

## Federated query: S3 evidence × Postgres reference tables × live CT log

One statement, three sources: the scanned certificates (Parquet on S3), the inequality inputs a security team edits
(Postgres), and what Certificate Transparency says right now (crt.sh, live).

```sql
SELECT a.asset_id, a.name, c.key_alg, c.key_bits, c.not_after AS crtsh_not_after, a.expires AS s3_expires,
       d.shelf_life_years AS x, m.migration_years AS y, (d.shelf_life_years + m.migration_years) AS x_plus_y
FROM mosca_s3.assets a
JOIN crtsh_pg.zaindroid_ct c ON a.negotiated_sig = CONCAT('crt.sh id ', CAST(c.crtsh_id AS STRING))
JOIN mosca_pg.data_classes d ON a.data_class = d.data_class
JOIN mosca_pg.migration_paths m ON a.kind = m.kind
WHERE a.in_use = true
ORDER BY c.not_after, a.asset_id
```

Result 2026-10-20 22:04 UTC: 12 rows in 4,866 ms. Every in-use certificate in the S3 evidence has the same expiry as
the live log; key types come from crt.sh (EC-256 ×6, RSA-2048 ×3, RSA-4096 ×3); x + y = 0 + 3 = 3 for all, so SAFE
under every anchor (x + y <= 4 years to 2030).

## Federated query: Postgres inventory × live CT log

Do the certificates in the inventory (scanned with `scan_ct.py`) still match what crt.sh says right now, and what
inequality inputs does each carry?

```sql
SELECT a.asset_id, a.name, a.in_use, a.expires AS inventory_expires, c.crtsh_id, c.key_alg, c.key_bits, c.not_after AS crtsh_not_after,
       CASE WHEN a.expires = c.not_after THEN 'match' ELSE 'DIFFERS' END AS expiry_check, d.shelf_life_years AS x, m.migration_years AS y
FROM mosca_pg.assets a
JOIN crtsh_pg.zaindroid_ct c ON a.negotiated_sig = CONCAT('crt.sh id ', CAST(c.crtsh_id AS STRING))
JOIN mosca_pg.data_classes d ON a.data_class = d.data_class
JOIN mosca_pg.migration_paths m ON a.kind = m.kind
WHERE a.source = 'ct_log' AND c.not_after >= CAST('2026-10-20' AS date)
ORDER BY c.not_after
```

Result, 2026-10-20 21:20 UTC, 12 rows in 5,054 ms (`timeUsed`):

| asset_id | name | in_use | inventory_expires | crtsh_id | key_alg | key_bits | crtsh_not_after | expiry_check | x | y |
|---|---|---|---|---|---|---|---|---|---|---|
| CT-708a92bb | CT: mean-machines.zaindroid.me | true | 2026-11-07 | 28687843651 | RSA | 2048 | 2026-11-07 | match | 0 | 3 |
| CT-1628fcf1 | CT: mean-machines.zaindroid.me | true | 2026-11-07 | 28687819082 | EC | 256 | 2026-11-07 | match | 0 | 3 |
| CT-82b898d7 | CT: hello.zaindroid.me | true | 2026-11-07 | 28671908333 | RSA | 4096 | 2026-11-07 | match | 0 | 3 |
| CT-275b8741 | CT: ivay-caller-portal.zaindroid.me | true | 2026-11-14 | 28888169873 | RSA | 4096 | 2026-11-14 | match | 0 | 3 |
| CT-cadbaae4 | CT: esp32-mesh.zaindroid.me | true | 2026-11-19 | 28998808475 | RSA | 4096 | 2026-11-19 | match | 0 | 3 |
| CT-f49bcff5 | CT: zaindroid.me | true | 2026-11-29 | 29668565953 | RSA | 2048 | 2026-11-29 | match | 0 | 3 |
| CT-75ddc6fb | CT: zaindroid.me | true | 2026-11-29 | 29458140400 | EC | 256 | 2026-11-29 | match | 0 | 3 |
| CT-79143f8b | CT: zaindroid.me | true | 2026-11-29 | 29458135923 | RSA | 2048 | 2026-11-29 | match | 0 | 3 |
| CT-b6ad3e2b | CT: zaindroid.me | true | 2026-11-29 | 29455955934 | EC | 256 | 2026-11-29 | match | 0 | 3 |
| CT-63a66063 | CT: zaindroid.me | true | 2026-11-29 | 29396812629 | EC | 256 | 2026-11-29 | match | 0 | 3 |
| CT-b731b8b0 | CT: zaindroid.me | true | 2026-12-01 | 29518744022 | EC | 256 | 2026-12-01 | match | 0 | 3 |
| CT-1a4d291b | CT: zaindroid.me | true | 2026-12-03 | 29556988686 | EC | 256 | 2026-12-03 | match | 0 | 3 |

Every live certificate in the inventory agrees with the live log; all have x = 0 (public_web) and y = 3 (cert), so
x + y = 3 ≤ 4 years to 2030: SAFE under every anchor (renewal, not migration). `mean-machines.zaindroid.me` no longer
resolves (probes.csv) but still holds two valid certificates until 2026-11-07.
