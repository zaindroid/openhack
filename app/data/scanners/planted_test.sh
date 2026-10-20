#!/usr/bin/env bash
# Planted-asset test: a temporary RSA-2048 certificate on a throwaway 127.0.0.1 port, served by OpenSSL 3.5 with
# classical groups only (X25519, P-256). The unmodified TLS scanner must find it, and the Skeptic must rate it LATE
# (data_class contracts: x=10, y=1 -> 11 > 9 years to 2035) with the hybrid-group action first
# (app/evals.planted.yaml). Everything is removed afterwards, and the real inventory must be byte-identical.
#   app/data/scanners/planted_test.sh            (from the repo root, on the host that holds app/data/inventory)
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
INV="$ROOT/app/data/inventory"
PY="${PYTHON:-$ROOT/.venv/bin/python}"
T=$(mktemp -d /tmp/mosca-planted.XXXXXX)
NAME=lab-mosca-planted
BEFORE=$(sha256sum "$INV"/*.csv | sha256sum | cut -c1-16)
PORT=$("$PY" -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')

cleanup() {
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  docker run --rm -v "$T:/p" alpine:3.22 rm -rf /p/inv >/dev/null 2>&1 || true
  rm -rf "$T"
  if (exec 3<>"/dev/tcp/127.0.0.1/$PORT") 2>/dev/null; then echo "CLEANUP FAILED: port $PORT still open"; exit 1; fi
  AFTER=$(sha256sum "$INV"/*.csv | sha256sum | cut -c1-16)
  [ "$BEFORE" = "$AFTER" ] && echo "cleanup: server stopped, port $PORT closed, files removed, inventory unchanged ($AFTER)" \
                           || { echo "CLEANUP FAILED: inventory changed $BEFORE -> $AFTER"; exit 1; }
}
trap cleanup EXIT

# 1. the planted asset: RSA-2048 self-signed certificate (key generated here, never reused)
"$PY" - "$T" <<'PY'
import datetime, sys
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
d = sys.argv[1]
k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
n = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "mosca-planted.test")])
now = datetime.datetime.now(datetime.timezone.utc)
c = (x509.CertificateBuilder().subject_name(n).issuer_name(n).public_key(k.public_key()).serial_number(x509.random_serial_number())
     .not_valid_before(now).not_valid_after(now + datetime.timedelta(days=30)).sign(k, hashes.SHA256()))
open(f"{d}/key.pem", "wb").write(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
open(f"{d}/cert.pem", "wb").write(c.public_bytes(serialization.Encoding.PEM))
PY
chmod 644 "$T"/*.pem
docker run -d --rm --name "$NAME" --network host -v "$T:/p:ro" alpine:3.22 sh -c \
  "apk add -q openssl >/dev/null && exec openssl s_server -accept 127.0.0.1:$PORT -cert /p/cert.pem -key /p/key.pem -groups X25519:P-256 -www -quiet" >/dev/null
for _ in $(seq 1 60); do (exec 3<>"/dev/tcp/127.0.0.1/$PORT") 2>/dev/null && break; sleep 1; done
echo "planted: RSA-2048 on 127.0.0.1:$PORT (groups X25519:P-256)"

# 2. the unmodified scanner finds it (its own targets file and inventory dir; the real ones are untouched)
cat > "$T/targets.yaml" <<Y
tls:
  - { host: "127.0.0.1", port: $PORT, name: "planted RSA-2048 test asset", data_class: contracts, note: "planted by planted_test.sh" }
Y
docker run --rm --name lab-mosca-scan-planted --network host -v "$ROOT:/w:ro" -v "$T:/p" -w /w/app/data/scanners \
  -e TARGETS=/p/targets.yaml -e INVENTORY_DIR=/p/inv alpine:3.22 sh -c \
  'apk add -q python3 py3-yaml py3-cryptography openssl >/dev/null && python3 scan_tls.py && chmod -R a+rwX /p/inv'

# 3. real inventory + the planted row, evaluated through the normal pipeline
mkdir -p "$T/seed"
cp "$INV"/assets.csv "$INV"/data_classes.csv "$INV"/migration_paths.csv "$INV"/scenarios.csv "$T/seed/"
tail -n +2 "$T/inv/assets.csv" >> "$T/seed/assets.csv"
"$PY" -c 'import csv,sys; [print("planted row:", r["asset_id"], r["kind"], r["algorithm"], "kex", r["negotiated_kex"], "|", r["negotiated_sig"], "|", r["data_class"]) for r in csv.DictReader(open(sys.argv[1]))]' "$T/inv/assets.csv"
grep -c "planted RSA-2048" "$T/seed/assets.csv" >/dev/null
cd "$ROOT"
SEED_DIR="$T/seed" MEMORY_DIR="$T/memory" "$PY" -m whycore.evals app/evals.planted.yaml
