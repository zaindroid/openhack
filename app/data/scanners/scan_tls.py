"""TLS inventory of your own endpoints: certificate key algorithm/bits/expiry (Python ssl) and, with `openssl` ≥ 3.5,
the negotiated TLS 1.3 group and signature type (shows X25519MLKEM768 when hybrid PQ is on). One ordinary handshake
per target (key_bits stays empty: the algorithm column is the key exchange; the certificate's key and size are in
negotiated_sig); the client offers X25519MLKEM768:X25519:secp256r1, so the result says what the server picks when hybrid is
on the table.

Target fields: host, port, name, data_class; optional sni (default host), starttls: postgres (send SSLRequest first),
in_use, note. Endpoints without TLS or not reachable are written to probes.csv, not to the inventory."""
from __future__ import annotations
import re, socket, ssl, subprocess
from common import append, log_probe, targets

PG_SSLREQUEST = bytes.fromhex("0000000804d2162f")


def _connect(host: str, port: int, starttls: str | None) -> socket.socket:
    s = socket.create_connection((host, port), timeout=8)
    if starttls == "postgres":
        s.sendall(PG_SSLREQUEST)
        if s.recv(1) != b"S":
            s.close()
            raise ConnectionError("postgres refused SSLRequest (server has no TLS)")
    return s


def cert_info(host: str, port: int, sni: str, starttls: str | None) -> dict:
    ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
    with _connect(host, port, starttls) as s, ctx.wrap_socket(s, server_hostname=sni) as t:
        der = t.getpeercert(binary_form=True); cipher = t.cipher(); proto = t.version()
    alg, bits, exp, subj = "unknown", "", "", ""
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives.asymmetric import ec, rsa, ed25519
        c = x509.load_der_x509_certificate(der); k = c.public_key()
        if isinstance(k, rsa.RSAPublicKey): alg, bits = "RSA", k.key_size
        elif isinstance(k, ec.EllipticCurvePublicKey): alg, bits = "ECDSA", k.curve.key_size
        elif isinstance(k, ed25519.Ed25519PublicKey): alg, bits = "Ed25519", 256
        exp = c.not_valid_after_utc.date().isoformat() if hasattr(c, "not_valid_after_utc") else c.not_valid_after.date().isoformat()
        subj = c.subject.rfc4514_string()[:60]
    except Exception as e:  # cryptography missing: keep the handshake facts only
        alg = f"unknown ({str(e)[:30]})"
    return {"cert_alg": alg, "bits": bits, "expires": exp, "cipher": cipher[0] if cipher else "", "proto": proto or "", "subject": subj}


def openssl_handshake(host: str, port: int, sni: str, starttls: str | None) -> dict:
    cmd = ["openssl", "s_client", "-connect", f"{host}:{port}", "-servername", sni, "-groups", "X25519MLKEM768:X25519:secp256r1", "-brief"]
    if starttls:
        cmd[2:2] = ["-starttls", starttls]
    try:
        ver = subprocess.run(["openssl", "version"], capture_output=True, timeout=5).stdout.decode()
        out = subprocess.run(cmd, input=b"", capture_output=True, timeout=20).stderr.decode(errors="ignore")
    except Exception:
        return {"group": "unknown (openssl not available)", "sig": ""}
    m = re.search(r"Negotiated TLS1.3 group:\s*(\S+)", out)          # openssl 3.5 prints this for hybrid groups
    t = re.search(r"(?:Peer|Server) Temp Key:\s*([^\n]+)", out)      # ... and this for classical ones
    s = re.search(r"Signature type:\s*(\S+)", out)
    if m:
        grp = m.group(1)
    elif t:
        parts = [p.strip() for p in t.group(1).split(",")]
        grp = parts[1] if parts[0] in ("ECDH", "DH") and len(parts) > 2 else parts[0]   # "X25519, 253 bits" / "ECDH, prime256v1, 256 bits"
    elif re.search(r"OpenSSL 3\.([5-9]|\d\d)", ver):
        p = re.search(r"Protocol version:\s*(\S+)", out)
        grp = f"none reported ({p.group(1) if p else 'handshake failed'})"
    else:
        grp = f"unknown (needs openssl ≥ 3.5, have {ver.split()[1] if ver else '?'})"
    return {"group": grp, "sig": s.group(1) if s else ""}


def main() -> None:
    rows = []
    for t in targets().get("tls", []):
        host, port = t["host"], int(t["port"]); sni = t.get("sni", host); st = t.get("starttls")
        label = f"{host}:{port}" + (f" sni={sni}" if sni != host else "")
        try:
            info = cert_info(host, port, sni, st)
        except Exception as e:
            log_probe("tls_scan", label, f"no TLS handshake: {type(e).__name__}: {str(e)[:100]}")
            print(label, "no TLS:", type(e).__name__, str(e)[:80])
            continue
        hs = openssl_handshake(host, port, sni, st)
        grp = hs["group"]
        kex_alg = "X25519" if "X25519" in grp.upper() else "ECDH"
        rows.append({"name": t.get("name", sni), "host": sni if sni != host else host, "port": port, "kind": "tls", "algorithm": kex_alg,
                     "key_bits": "", "purpose": "confidentiality", "negotiated_kex": grp,
                     "negotiated_sig": f"{info['cert_alg']}-{info['bits']} cert" + (f", {hs['sig']}" if hs["sig"] else ""),
                     "expires": info["expires"], "in_use": t.get("in_use", True), "data_class": t.get("data_class", "logs"),
                     "note": "; ".join(x for x in [f"connect {host}:{port}" if sni != host else "", f"{info['proto']} {info['cipher']}",
                                                   f"cert {info['subject']}", t.get("note", "")] if x)})
        print(label, grp, info["cert_alg"], info["bits"], info["expires"])
    print("written:", append(rows, "tls_scan"))


if __name__ == "__main__":
    main()
