"""TLS inventory of your own endpoints: certificate key algorithm/bits/expiry (Python ssl) and, when `openssl` ≥ 3.5 is
installed, the negotiated TLS 1.3 group (shows X25519MLKEM768 when hybrid PQ is on). One ordinary handshake per host."""
from __future__ import annotations
import re, socket, ssl, subprocess
from datetime import datetime
from common import append, targets


def cert_info(host: str, port: int) -> dict:
    ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
    with socket.create_connection((host, port), timeout=8) as s, ctx.wrap_socket(s, server_hostname=host) as t:
        der = t.getpeercert(binary_form=True); cipher = t.cipher()
    alg, bits, exp = "unknown", "", ""
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives.asymmetric import ec, rsa, ed25519
        c = x509.load_der_x509_certificate(der); k = c.public_key()
        if isinstance(k, rsa.RSAPublicKey): alg, bits = "RSA", k.key_size
        elif isinstance(k, ec.EllipticCurvePublicKey): alg, bits = "ECDSA", k.curve.key_size
        elif isinstance(k, ed25519.Ed25519PublicKey): alg, bits = "Ed25519", 256
        exp = c.not_valid_after_utc.date().isoformat() if hasattr(c, "not_valid_after_utc") else c.not_valid_after.date().isoformat()
    except Exception as e:  # cryptography missing: keep the handshake facts only
        alg = f"unknown ({str(e)[:30]})"
    return {"cert_alg": alg, "bits": bits, "expires": exp, "cipher": cipher[0] if cipher else ""}


def negotiated_group(host: str, port: int) -> str:
    try:
        out = subprocess.run(["openssl", "s_client", "-connect", f"{host}:{port}", "-servername", host, "-groups", "X25519MLKEM768:X25519:secp256r1", "-brief"],
                             input=b"", capture_output=True, timeout=15).stderr.decode(errors="ignore")
        m = re.search(r"Negotiated TLS1.3 group:\s*(\S+)", out)
        return m.group(1) if m else ("X25519 (group not reported by this openssl)")
    except Exception:
        return "unknown (openssl not available)"


def main() -> None:
    rows = []
    for t in targets().get("tls", []):
        info = cert_info(t["host"], int(t["port"])); grp = negotiated_group(t["host"], int(t["port"]))
        kex_alg = "X25519" if "X25519" in grp.upper() or "MLKEM" in grp.upper() else "ECDH"
        rows.append({"name": t.get("name", t["host"]), "host": t["host"], "port": t["port"], "kind": "tls", "algorithm": kex_alg,
                     "key_bits": info["bits"], "purpose": "confidentiality", "negotiated_kex": grp, "negotiated_sig": f"{info['cert_alg']}-{info['bits']} cert",
                     "expires": info["expires"], "data_class": t.get("data_class", "logs"), "note": f"cipher {info['cipher']}"})
        print(t["host"], grp, info)
    print("written:", append(rows, "tls_scan"))


if __name__ == "__main__":
    main()
