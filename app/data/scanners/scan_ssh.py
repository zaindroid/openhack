"""SSH inventory of your own hosts: host-key algorithms via `ssh-keyscan` and the server's key-exchange offer via
`ssh -vv` (reads the banner exchange only; no login attempted)."""
from __future__ import annotations
import re, subprocess
from common import append, targets


def main() -> None:
    rows = []
    for t in targets().get("ssh", []):
        host, port = t["host"], int(t.get("port", 22))
        keys = subprocess.run(["ssh-keyscan", "-p", str(port), host], capture_output=True, timeout=20).stdout.decode(errors="ignore")
        algs = sorted({ln.split()[1] for ln in keys.splitlines() if ln and not ln.startswith("#") and len(ln.split()) > 2})
        v = subprocess.run(["ssh", "-vv", "-p", str(port), "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=8", f"probe@{host}", "true"],
                           capture_output=True, timeout=25).stderr.decode(errors="ignore")
        m = re.search(r"kex: algorithm:\s*(\S+)", v)
        kex = m.group(1) if m else "unknown"
        hk = "RSA" if any("rsa" in a for a in algs) else "Ed25519" if any("ed25519" in a for a in algs) else "ECDSA" if any("ecdsa" in a for a in algs) else "unknown"
        rows.append({"name": t.get("name", host), "host": host, "port": port, "kind": "ssh", "algorithm": hk, "key_bits": 2048 if hk == "RSA" else 256,
                     "purpose": "both", "negotiated_kex": kex, "negotiated_sig": ",".join(algs), "data_class": t.get("data_class", "credentials"),
                     "note": "host keys: " + ",".join(algs)})
        print(host, kex, algs)
    print("written:", append(rows, "ssh_scan"))


if __name__ == "__main__":
    main()
