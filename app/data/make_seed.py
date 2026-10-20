"""Writes app/data/seed/*.csv: an ILLUSTRATIVE inventory of a small mixed estate (edge proxy, origin, SSH fleet,
firmware-signed devices, a VPN, documents) plus the lookup tables. Real inventories come from app/data/scanners/
(run on a machine that can reach your own hosts) and land in the same schema.

Shelf-life and migration-time tables are the judgement calls a security team makes; they are data, not prompts."""
from __future__ import annotations
import csv, os, sys
import yaml

HERE = os.path.dirname(__file__)
SEED = os.path.join(HERE, "seed")
ALG = yaml.safe_load(open(os.path.join(HERE, "..", "algorithms.yaml")))

ASSET_COLS = ["asset_id", "name", "host", "port", "kind", "algorithm", "key_bits", "purpose", "negotiated_kex", "negotiated_sig",
              "expires", "in_use", "data_class", "traffic_gb_month", "source", "found_at", "note"]

# kind: tls | ssh | vpn | cert | firmware_sig | repo_key | doc_sig
ASSETS = [
    # edge: hybrid PQ already negotiated → SAFE (the Skeptic must recognise this and not raise an alarm)
    ["A01", "public edge (CDN)", "www.example-estate.net", 443, "tls", "X25519", 256, "confidentiality", "X25519MLKEM768", "ecdsa_secp256r1_sha256", "2027-01-15", True, "public_web", 900, "tls_scan", "2026-10-20", "edge terminates TLS with hybrid ML-KEM"],
    # origin behind the edge: classical only, protects contracts → LATE
    ["A02", "origin reverse proxy", "origin.internal", 443, "tls", "X25519", 256, "confidentiality", "X25519", "rsa_pss_rsae_sha256", "2027-03-01", True, "contracts", 120, "tls_scan", "2026-10-20", "edge→origin hop is classical; RSA-2048 origin cert"],
    ["A03", "admin SSH (servingz)", "servingz.internal", 22, "ssh", "Ed25519", 256, "both", "curve25519-sha256", "ssh-ed25519", "", True, "credentials", 2, "ssh_scan", "2026-10-20", "host key Ed25519, classical kex"],
    ["A04", "rpi-01 SSH", "rpi-01.internal", 22, "ssh", "RSA", 2048, "both", "curve25519-sha256", "rsa-sha2-512", "", True, "telemetry", 1, "ssh_scan", "2026-10-20", "RSA host key"],
    ["A05", "rpi-02 SSH", "rpi-02.internal", 22, "ssh", "RSA", 2048, "both", "curve25519-sha256", "rsa-sha2-512", "", True, "telemetry", 1, "ssh_scan", "2026-10-20", ""],
    ["A06", "jetson SSH", "jetson.internal", 22, "ssh", "Ed25519", 256, "both", "curve25519-sha256", "ssh-ed25519", "", True, "credentials", 3, "ssh_scan", "2026-10-20", ""],
    # field devices: firmware signatures must stay trustworthy for the device lifetime → forgery risk
    ["A07", "ESP32 node firmware signing", "esp32-fleet", "", "firmware_sig", "ECDSA", 256, "signature", "", "ecdsa_p256_sha256", "", True, "device_lifetime", 0, "firmware_scan", "2026-10-20", "secure-boot key ECDSA P-256; devices in field ≥10 y"],
    ["A08", "nRF5340 firmware signing", "nrf5340-dk", "", "firmware_sig", "ECDSA", 256, "signature", "", "ecdsa_p256_sha256", "", True, "device_lifetime", 0, "firmware_scan", "2026-10-20", "bootloader verifies ECDSA; demo target for ML-DSA-44"],
    # a long-lived private key committed in a repo (hygiene + quantum)
    ["A09", "deploy key in repo", "git/infra-repo", "", "repo_key", "RSA", 4096, "both", "", "", "", True, "credentials", 0, "repo_scan", "2026-10-20", "PEM private key in deploy/ (should not be in a repo at all)"],
    # VPN: classical key exchange, protects admin traffic
    ["A10", "site VPN", "vpn.internal", 51820, "vpn", "X25519", 256, "confidentiality", "X25519", "", "", True, "credentials", 40, "config_scan", "2026-10-20", "WireGuard; no PSK layer"],
    # signed documents with long validity
    ["A11", "signed contracts (PDF)", "docs/contracts", "", "doc_sig", "RSA", 2048, "signature", "", "rsa_pkcs1_sha256", "2036-12-31", True, "contracts", 0, "doc_scan", "2026-10-20", "signatures must verify for 10 y"],
    # dead asset: expired certificate for a decommissioned host
    ["A12", "legacy host cert", "old.example-estate.net", 443, "cert", "RSA", 2048, "both", "", "rsa_pkcs1_sha256", "2025-06-30", False, "public_web", 0, "ct_log", "2026-10-20", "expired; host decommissioned"],
    # internal datastores
    ["A13", "object store TLS", "minio.internal", 9000, "tls", "X25519", 256, "confidentiality", "X25519", "rsa_pss_rsae_sha256", "2027-05-01", True, "backups", 300, "tls_scan", "2026-10-20", ""],
    ["A14", "database TLS", "postgres.internal", 5432, "tls", "X25519", 256, "confidentiality", "X25519", "ecdsa_secp256r1_sha256", "2027-05-01", True, "customer_records", 60, "tls_scan", "2026-10-20", ""],
    ["A15", "metrics endpoint TLS", "metrics.internal", 443, "tls", "X25519", 256, "confidentiality", "X25519", "ecdsa_secp256r1_sha256", "2027-02-01", True, "logs", 15, "tls_scan", "2026-10-20", ""],
]

DATA_CLASSES = [  # shelf_life_years = how long the protected data must stay confidential / the signature must stay trustworthy
    ["public_web", 0, "public pages; confidentiality value ~0"],
    ["logs", 1, "operational logs"],
    ["telemetry", 1, "sensor telemetry"],
    ["credentials", 5, "admin sessions, keys, tokens (rotated, but reused secrets live on)"],
    ["backups", 7, "encrypted backups kept 7 years"],
    ["contracts", 10, "commercial contracts; legal retention 10 years"],
    ["device_lifetime", 12, "firmware trust must hold for the device's service life"],
    ["customer_records", 15, "personal data with long retention"],
    ["health_records", 30, "medical records"],
]

MIGRATION = [  # migration_years = realistic time from decision to fully migrated, per asset kind
    ["tls", 1.0, True, "hybrid groups available in OpenSSL 3.5+, major CDNs, nginx 1.27+"],
    ["ssh", 0.5, True, "OpenSSH 9.9+ ships mlkem768x25519-sha256"],
    ["vpn", 2.0, False, "interim PSK layer; vendor hybrid KEM pending"],
    ["cert", 3.0, False, "WebPKI PQ certificates not generally issued yet"],
    ["firmware_sig", 2.0, True, "pqm4 ML-DSA on Cortex-M; fleet re-provisioning takes time"],
    ["repo_key", 0.25, True, "rotate and remove from repo"],
    ["doc_sig", 3.0, False, "re-sign/timestamp archives when PQ document signatures are supported"],
]


def main() -> None:
    os.makedirs(SEED, exist_ok=True)
    with open(os.path.join(SEED, "assets.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(ASSET_COLS); w.writerows(ASSETS)
    with open(os.path.join(SEED, "data_classes.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["data_class", "shelf_life_years", "examples"]); w.writerows(DATA_CLASSES)
    with open(os.path.join(SEED, "migration_paths.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["kind", "migration_years", "vendor_ready", "note"]); w.writerows(MIGRATION)
    with open(os.path.join(SEED, "scenarios.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["scenario", "z_year", "note"])
        for s in ALG["scenarios"]:
            w.writerow([s["id"], s["z_year"], s["note"]])
    with open(os.path.join(SEED, "README.md"), "w") as f:
        f.write("# ILLUSTRATIVE inventory\n\nThese CSVs describe a small invented estate so the agent runs without any scan. "
                "Hostnames are placeholders. Replace with the output of `app/data/scanners/` (same columns) for a real run. "
                "`scenarios.csv` is generated from `app/algorithms.yaml`; edit the YAML, not the CSV.\n")
    print("seed written:", len(ASSETS), "assets")


if __name__ == "__main__":
    main()
