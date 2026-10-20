"""Certificate Transparency lookup for your own domains via crt.sh (public, read-only). Finds certificates you may have
forgotten: old hostnames, expired or still-valid, and their key algorithms.

Primary source: crt.sh's public Postgres (guest@crt.sh:5432/certwatch), which returns key algorithm and size for every
certificate in one query. Fallback: the JSON API (frequently 502), where key type is not available. One row per
certificate serial (a precertificate and its final certificate share one). in_use is true while unexpired.
Only names equal to or under each listed domain are kept."""
from __future__ import annotations
import hashlib, time
from datetime import date
import httpx
from common import append, targets

UA = {"User-Agent": "mosca-inventory (own domains only)"}
SQL = """SELECT c.ID AS id, encode(x509_serialNumber(c.CERTIFICATE), 'hex') AS serial, x509_notAfter(c.CERTIFICATE) AS not_after,
       x509_keyAlgorithm(c.CERTIFICATE) AS key_alg, x509_keySize(c.CERTIFICATE) AS key_bits, x509_issuerName(c.CERTIFICATE) AS issuer,
       x509_commonName(c.CERTIFICATE) AS cn, (SELECT string_agg(n, ',') FROM x509_altNames(c.CERTIFICATE) n) AS names
FROM certificate c WHERE plainto_tsquery('certwatch', %(dom)s) @@ identities(c.CERTIFICATE)"""
ALG = {"EC": "ECDSA", "RSA": "RSA", "Ed25519": "Ed25519"}


def from_postgres(dom: str) -> list[dict]:
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(host="crt.sh", port=5432, user="guest", dbname="certwatch", autocommit=True, row_factory=dict_row, connect_timeout=30) as c:
        rows = c.execute(SQL, {"dom": dom}).fetchall()
    return [{"id": r["id"], "serial": r["serial"], "not_after": str(r["not_after"])[:10], "alg": ALG.get(r["key_alg"], r["key_alg"] or "unknown"),
             "bits": str(r["key_bits"] or ""), "issuer": r["issuer"] or "", "cn": r["cn"] or "", "names": (r["names"] or r["cn"] or "").split(","),
             "via": "crt.sh postgres"} for r in rows]


def from_json(dom: str) -> list[dict]:
    out = []
    for q in (f"%.{dom}", dom):
        for attempt in range(3):
            r = httpx.get("https://crt.sh/", params={"q": q, "output": "json"}, timeout=120, headers=UA)
            if r.status_code == 200:
                break
            time.sleep(10 * (attempt + 1))
        r.raise_for_status()
        out += [{"id": e["id"], "serial": e.get("serial_number") or str(e["id"]), "not_after": e.get("not_after", "")[:10],
                 "alg": "unknown (crt.sh JSON has no key type)", "bits": "", "issuer": e.get("issuer_name", ""), "cn": e.get("common_name", ""),
                 "names": e.get("name_value", "").split("\n"), "via": "crt.sh json"} for e in r.json()]
    return out


def main() -> None:
    rows, today = [], date.today().isoformat()
    for dom in targets().get("domains", []):
        try:
            certs = from_postgres(dom)
        except Exception as e:
            print("crt.sh postgres failed:", type(e).__name__, str(e)[:100], "- falling back to JSON")
            certs = from_json(dom)
        by_serial: dict[str, dict] = {}
        for c in certs:
            names = sorted({n.strip().lower() for n in c["names"] if n.strip()})
            if not any(n == dom or n.endswith("." + dom) for n in names):
                continue
            c["names"] = names
            by_serial.setdefault(c["serial"], c)
        live = 0
        for serial, c in sorted(by_serial.items(), key=lambda kv: kv[1]["not_after"]):
            in_use = c["not_after"] >= today
            live += in_use
            rows.append({"asset_id": f"CT-{hashlib.sha1(serial.encode()).hexdigest()[:8]}", "name": f"CT: {c['cn'] or c['names'][0]}",
                         "host": ",".join(c["names"])[:200], "port": 443, "kind": "cert", "algorithm": c["alg"], "key_bits": c["bits"],
                         "purpose": "both", "expires": c["not_after"], "in_use": in_use, "data_class": "public_web",
                         "negotiated_sig": f"crt.sh id {c['id']}",
                         "note": f"serial {serial}; issuer {c['issuer'][:60]}; via {c['via']}"})
        print(dom, len(by_serial), "certificates,", live, "unexpired")
    print("written:", append(rows, "ct_log"))


if __name__ == "__main__":
    main()
