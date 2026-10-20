"""Finds public-key algorithm identifiers inside firmware images you build: DER AlgorithmIdentifier OIDs for RSA, EC,
Ed25519 and the ML-DSA family. Tells you which verifier keys a device trusts — the input for the firmware-signing plan."""
from __future__ import annotations
import os
from common import append, log_probe, targets

OIDS = {
    "RSA (rsaEncryption 1.2.840.113549.1.1.1)": bytes.fromhex("06092a864886f70d010101"),
    "ECDSA (ecPublicKey 1.2.840.10045.2.1)": bytes.fromhex("06072a8648ce3d0201"),
    "Ed25519 (1.3.101.112)": bytes.fromhex("06032b6570"),
    "ML-DSA-44 (2.16.840.1.101.3.4.3.17)": bytes.fromhex("0609608648016503040311"),
    "ML-DSA-65 (2.16.840.1.101.3.4.3.18)": bytes.fromhex("0609608648016503040312"),
    "ML-DSA-87 (2.16.840.1.101.3.4.3.19)": bytes.fromhex("0609608648016503040313"),
}


def main() -> None:
    rows = []
    for t in targets().get("firmware", []) or []:
        if not os.path.exists(t["path"]):
            log_probe("firmware_scan", t["path"], "file not found"); print(t["path"], "not found"); continue
        blob = open(t["path"], "rb").read()
        found = [name for name, oid in OIDS.items() if oid in blob]
        if not found:   # no evidence of a public-key use is not an asset: an "unknown" signature row would be rated as
                        # a classical signer with the device's shelf life (LATE) on no evidence at all
            log_probe("firmware_scan", t["path"], f"no public-key algorithm identifiers in {len(blob)} bytes (no DER verifier key; raw keys are not detected)")
            print(t["path"], "no OIDs found; logged to probes.csv"); continue
        alg = "ML-DSA" if any("ML-DSA" in f for f in found) else "RSA" if any(f.startswith("RSA") for f in found) else "ECDSA" if any(f.startswith("ECDSA") for f in found) else "Ed25519" if any(f.startswith("Ed25519") for f in found) else "none found"
        rows.append({"name": t.get("name", t["path"]), "host": t["path"], "port": "", "kind": "firmware_sig", "algorithm": alg,
                     "key_bits": 256 if alg in ("ECDSA", "Ed25519") else "", "purpose": "signature", "negotiated_sig": ";".join(found),
                     "data_class": t.get("data_class", "device_lifetime"), "note": f"{len(blob)} bytes scanned; OIDs: {found or 'none (raw keys without DER are not detected)'}"})
        print(t["path"], found)
    print("written:", append(rows, "firmware_scan"))


if __name__ == "__main__":
    main()
