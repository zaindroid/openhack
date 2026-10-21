#!/usr/bin/env bash
# The demo fixture (docs/demo.md): a real, owned, throwaway TLS endpoint that starts classical-only.
#   up       start lab-mosca-demo-tls on groundswell-net (RSA-2048, groups X25519:P-256), then rescan
#   rescan   scan only the targets.yaml `demo:` entries; upsert their rows; reload Postgres; publish to S3
#   apply    what an Approve does, by hand: switch the fixture to X25519MLKEM768:X25519 (fallback if the app cannot)
#   status   the fixture's current group list
#   down     remove the container and its rows; the inventory must equal the copy saved by `up`
# Run on servingz from the repo root. DEMO_APPLY_TOKEN lives in infra/.env (made by `up`; never printed).
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
INV="$ROOT/app/data/inventory"
SC="$ROOT/app/data/scanners"
PY="${PYTHON:-$ROOT/.venv/bin/python}"
NAME=lab-mosca-demo-tls
NET=groundswell-net
PG=$(docker ps --format '{{.Names}}' | grep '^lab-mosca-pg-' | head -1)
ENV="$ROOT/infra/.env"

token() {
  grep -q '^DEMO_APPLY_TOKEN=' "$ENV" || echo "DEMO_APPLY_TOKEN=$("$PY" -c 'import secrets; print(secrets.token_urlsafe(32))')" >> "$ENV"
  grep -q '^DEMO_APPLY_URL=' "$ENV" || echo "DEMO_APPLY_URL=http://$NAME:8080" >> "$ENV"
  # the apply allow-list: host:port of every targets.yaml demo: entry marked `apply: true`
  sed -i '/^APPLY_ALLOW=/d' "$ENV"
  echo "APPLY_ALLOW=$("$PY" -c 'import sys, yaml; print(",".join(f"{t["host"]}:{t["port"]}" for t in (yaml.safe_load(open(sys.argv[1])) or {}).get("demo", []) if t.get("apply") is True))' "$SC/targets.yaml")" >> "$ENV"
  grep '^DEMO_APPLY_TOKEN=' "$ENV" | cut -d= -f2-
}

load_pg() {   # one transaction; the CSV is copied in and removed again
  local h; h=$(head -1 "$INV/assets.csv" | tr -d '\r')
  docker cp -q "$INV/assets.csv" "$PG:/tmp/assets.csv"
  docker exec "$PG" psql -q -v ON_ERROR_STOP=1 -U mosca -d mosca -c "BEGIN" -c "TRUNCATE assets" \
    -c "COPY assets($h) FROM '/tmp/assets.csv' WITH (FORMAT csv, HEADER true)" -c "COMMIT"
  docker exec "$PG" rm -f /tmp/assets.csv
}

publish() { load_pg; "$PY" "$SC/publish_s3.py" | grep current/assets; }

rescan() {
  docker run --rm --name lab-mosca-scan-demo --network "$NET" -v "$ROOT:/w:ro" -v "$INV:/inv" -w /w/app/data/scanners \
    -e INVENTORY_DIR=/inv -e TARGETS=/w/app/data/scanners/targets.yaml alpine:3.22 sh -c \
    'apk add -q python3 py3-yaml py3-cryptography openssl >/dev/null && python3 scan_tls.py --demo && chmod a+rw /inv/assets.csv /inv/probes.csv'
  publish
}

case "${1:-}" in
  up)
    TOK=$(token)
    [ -f "$INV/.pre-demo-assets.csv" ] || cp "$INV/assets.csv" "$INV/.pre-demo-assets.csv"
    docker rm -f "$NAME" >/dev/null 2>&1 || true
    docker run -d --name "$NAME" --network "$NET" --network-alias "$NAME" --memory 64m --restart no \
      -e DEMO_APPLY_TOKEN="$TOK" -v "$SC/demo_fixture_server.py:/srv/fixture.py:ro" alpine:3.22 sh -c \
      'apk add -q python3 py3-cryptography openssl >/dev/null && exec python3 -u /srv/fixture.py' >/dev/null
    for _ in $(seq 1 60); do docker logs "$NAME" 2>&1 | grep -q 's_server :8443' && break; sleep 1; done
    docker logs "$NAME" 2>&1 | tail -1
    rescan ;;
  rescan) rescan ;;
  apply)
    TOK=$(token)
    docker exec -e T="$TOK" "$NAME" python3 -c 'import json, os, urllib.request as u
r = u.Request("http://127.0.0.1:8080/apply", data=json.dumps({"groups": "X25519MLKEM768:X25519"}).encode(), headers={"Authorization": "Bearer " + os.environ["T"], "content-type": "application/json"})
print(u.urlopen(r).read().decode())' ;;
  status) docker exec "$NAME" wget -qO- http://127.0.0.1:8080/state; echo ;;
  down)
    docker rm -f "$NAME" >/dev/null 2>&1 || true
    "$PY" - "$INV/assets.csv" <<'PY'
import csv, sys
p = sys.argv[1]
rows = list(csv.DictReader(open(p, newline="")))
keep = [r for r in rows if "DEMO FIXTURE" not in r["note"]]
w = csv.DictWriter(open(p, "w", newline=""), fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(keep)
print(f"removed {len(rows) - len(keep)} demo row(s)")
PY
    if [ -f "$INV/.pre-demo-assets.csv" ]; then
      cmp -s "$INV/assets.csv" "$INV/.pre-demo-assets.csv" && echo "inventory equals the pre-demo copy" && rm "$INV/.pre-demo-assets.csv" \
        || { echo "INVENTORY DIFFERS from the pre-demo copy ($INV/.pre-demo-assets.csv kept)"; exit 1; }
    fi
    publish
    sed -i '/^DEMO_APPLY_TOKEN=/d;/^DEMO_APPLY_URL=/d;/^APPLY_ALLOW=/d' "$ENV"
    echo "fixture removed; remove DEMO_APPLY_URL, DEMO_APPLY_TOKEN and APPLY_ALLOW from the lab-mosca Coolify env too" ;;
  *) echo "usage: $0 up|rescan|apply|status|down"; exit 2 ;;
esac
