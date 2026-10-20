"""Certificate Transparency lookup for your own domains via crt.sh (public, read-only). Finds certificates you may have
forgotten: old hostnames, expired or still-valid, and their key algorithms."""
from __future__ import annotations
import httpx
from common import append, targets


def main() -> None:
    rows = []
    for dom in targets().get("domains", []):
        js = httpx.get("https://crt.sh/", params={"q": f"%.{dom}", "output": "json"}, timeout=60, headers={"User-Agent": "mosca-inventory"}).json()
        seen = set()
        for e in js:
            name = e.get("common_name") or e.get("name_value", "").split("\n")[0]
            key = (name, e.get("not_after", "")[:10])
            if key in seen:
                continue
            seen.add(key)
            rows.append({"name": f"CT: {name}", "host": name, "port": 443, "kind": "cert", "algorithm": "unknown (fetch cert for key type)", "key_bits": "",
                         "purpose": "both", "expires": e.get("not_after", "")[:10], "in_use": False, "data_class": "public_web",
                         "note": f"issuer {e.get('issuer_name', '')[:60]}; logged {e.get('entry_timestamp', '')[:10]}"})
        print(dom, len(seen), "certificates")
    print("written:", append(rows, "ct_log"))


if __name__ == "__main__":
    main()
