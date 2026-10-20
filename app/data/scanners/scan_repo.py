"""Finds key material and signature-algorithm choices in repositories you own: PEM and OpenSSH private/public keys
(type and size), JWT `alg` settings (JSON/JS objects and PyJWT-style `algorithm(s)=`), per file. Nothing leaves the
machine; only metadata is written. Whether a key file is tracked by git or ignored is recorded in the note (a key that
is gitignored is still a key on disk, but it is not in the repository history).

Target fields: path, data_class; optional exclude: [subdir names] for vendored or third-party trees."""
from __future__ import annotations
import os, re, subprocess
from common import append, targets

PEM = re.compile(rb"-----BEGIN (RSA |EC |OPENSSH |ENCRYPTED |DSA |)(PRIVATE|PUBLIC) KEY-----")
JWT = [re.compile(rb"[\"']alg[\"']\s*:\s*[\"'](RS|ES|PS|EdDSA|HS)(\d{3})?[\"']"),
       re.compile(rb"\balgorithms?\s*=\s*\[?\s*[\"'](RS|ES|PS|EdDSA|HS)(\d{3})?[\"']")]
JWT_ALG = {"RS": "RSA", "PS": "RSA", "ES": "ECDSA", "EdDSA": "Ed25519", "HS": "HMAC"}
SKIP = {".git", "node_modules", ".venv", "venv", "__pycache__", "site-packages", ".pytest_cache"}


def key_type(blob: bytes) -> tuple[str, str]:
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec, rsa, ed25519, dsa
        if b"OPENSSH PRIVATE" in blob:
            k = serialization.load_ssh_private_key(blob, password=None)
        elif b"PRIVATE" in blob:
            k = serialization.load_pem_private_key(blob, password=None)
        else:
            k = serialization.load_pem_public_key(blob)
        if isinstance(k, (rsa.RSAPrivateKey, rsa.RSAPublicKey)): return "RSA", str(k.key_size)
        if isinstance(k, (ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey)): return "ECDSA", str(k.curve.key_size)
        if isinstance(k, (ed25519.Ed25519PrivateKey, ed25519.Ed25519PublicKey)): return "Ed25519", "256"
        if isinstance(k, (dsa.DSAPrivateKey, dsa.DSAPublicKey)): return "DSA", str(k.key_size)
    except Exception as e:
        m = PEM.search(blob)
        kind = (m.group(1).decode().strip() or "PKCS8") if m else "unknown"
        return f"unknown ({kind}; {type(e).__name__})", ""
    return "unknown", ""


def git_state(path: str) -> str:
    d = os.path.dirname(path)
    try:
        if subprocess.run(["git", "-C", d, "ls-files", "--error-unmatch", path], capture_output=True, timeout=10).returncode == 0:
            return "tracked in git"
        if subprocess.run(["git", "-C", d, "check-ignore", "-q", path], capture_output=True, timeout=10).returncode == 0:
            return "gitignored"
        if subprocess.run(["git", "-C", d, "rev-parse"], capture_output=True, timeout=10).returncode == 0:
            return "untracked"
    except Exception:
        pass
    return "not a git repo"


def main() -> None:
    rows = []
    for t in targets().get("repos", []):
        excl = set(t.get("exclude", []))
        for root, dirs, files in os.walk(t["path"]):
            dirs[:] = [d for d in dirs if d not in SKIP and d not in excl]
            for fn in files:
                p = os.path.join(root, fn)
                rel = os.path.relpath(p, t["path"])
                try:
                    blob = open(p, "rb").read(200_000)
                except Exception:
                    continue
                if PEM.search(blob):
                    alg, bits = key_type(blob)
                    private = b"PRIVATE" in PEM.search(blob).group(0)
                    rows.append({"name": f"key file {rel}", "host": t["path"], "port": "", "kind": "repo_key", "algorithm": alg, "key_bits": bits,
                                 "purpose": "both", "data_class": t.get("data_class", "credentials"),
                                 "note": f"{'PRIVATE' if private else 'public'} key; {git_state(p)}"})
                algs = sorted({(m.group(1) + (m.group(2) or b"")).decode() for rx in JWT for m in rx.finditer(blob)})
                for alg in algs:
                    fam = re.match(r"[A-Za-z]+?(?=\d|$)", alg).group(0)
                    rows.append({"name": f"JWT alg {alg} in {rel}", "host": t["path"], "port": "", "kind": "doc_sig",
                                 "algorithm": JWT_ALG.get(fam, fam), "key_bits": "", "purpose": "signature",
                                 "data_class": t.get("data_class", "credentials"), "note": f"token signature algorithm; {git_state(p)}"})
    print(len(rows), "findings"); print("written:", append(rows, "repo_scan"))


if __name__ == "__main__":
    main()
