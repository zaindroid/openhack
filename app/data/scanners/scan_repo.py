"""Finds key material and signature-algorithm choices in repositories you own: PEM private/public keys (type and size),
JWT `alg` settings, and well-known key file extensions. Nothing leaves the machine; only metadata is written."""
from __future__ import annotations
import os, re
from common import append, targets

PEM = re.compile(rb"-----BEGIN (RSA |EC |OPENSSH |ENCRYPTED |)(PRIVATE|PUBLIC) KEY-----")
JWT = re.compile(rb"[\"']alg[\"']\s*:\s*[\"'](RS|ES|PS|EdDSA|HS)(\d{3})?[\"']")
SKIP = {".git", "node_modules", ".venv", "__pycache__"}


def key_type(path: str, blob: bytes) -> tuple[str, str]:
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec, rsa, ed25519
        k = serialization.load_pem_private_key(blob, password=None) if b"PRIVATE" in blob else serialization.load_pem_public_key(blob)
        if isinstance(k, (rsa.RSAPrivateKey, rsa.RSAPublicKey)): return "RSA", str(k.key_size)
        if isinstance(k, (ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey)): return "ECDSA", str(k.curve.key_size)
        if isinstance(k, (ed25519.Ed25519PrivateKey, ed25519.Ed25519PublicKey)): return "Ed25519", "256"
    except Exception:
        pass
    m = PEM.search(blob)
    return (m.group(1).decode().strip() or "unknown"), ""


def main() -> None:
    rows = []
    for t in targets().get("repos", []):
        for root, dirs, files in os.walk(t["path"]):
            dirs[:] = [d for d in dirs if d not in SKIP]
            for fn in files:
                p = os.path.join(root, fn)
                try:
                    blob = open(p, "rb").read(200_000)
                except Exception:
                    continue
                if PEM.search(blob):
                    alg, bits = key_type(p, blob)
                    rows.append({"name": f"key file {os.path.relpath(p, t['path'])}", "host": t["path"], "port": "", "kind": "repo_key", "algorithm": alg, "key_bits": bits,
                                 "purpose": "both", "data_class": t.get("data_class", "credentials"), "note": "PEM block in repository" + (" (PRIVATE)" if b"PRIVATE" in blob else "")})
                for m in JWT.finditer(blob):
                    alg = (m.group(1) + (m.group(2) or b"")).decode()
                    rows.append({"name": f"JWT alg {alg} in {os.path.relpath(p, t['path'])}", "host": t["path"], "port": "", "kind": "doc_sig",
                                 "algorithm": {"RS": "RSA", "PS": "RSA", "ES": "ECDSA", "EdDSA": "Ed25519", "HS": "HMAC"}[m.group(1).decode()], "key_bits": "",
                                 "purpose": "signature", "data_class": t.get("data_class", "credentials"), "note": "token signature algorithm"})
    print(len(rows), "findings"); print("written:", append(rows, "repo_scan"))


if __name__ == "__main__":
    main()
