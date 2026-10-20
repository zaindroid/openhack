"""CycloneDX 1.6 Cryptographic Bill of Materials (CBOM) export of the inventory, with Mosca's verdicts as properties.
Run hook (RUN_HOOKS=...,app.cbom:attach) → run.extras["cbom"], downloadable at /runs/{id}/extras/cbom.
CLI: python -m app.cbom > cbom.json (inventory only, no verdicts)."""
from __future__ import annotations
import json, sys, time, uuid

PRIMITIVE = {"RSA": "pke", "ECDSA": "signature", "Ed25519": "signature", "X25519": "key-agree", "ECDH": "key-agree", "DH": "key-agree",
             "ML-KEM": "kem", "ML-DSA": "signature", "SLH-DSA": "signature", "HMAC": "mac", "AES-128": "block-cipher", "AES-256": "block-cipher"}


def component(a: dict, verdicts: dict | None = None) -> dict:
    alg = str(a.get("algorithm", "unknown"))
    props = [{"name": f"mosca:{k}", "value": str(v)} for k, v in a.items() if k in ("kind", "purpose", "negotiated_kex", "negotiated_sig", "data_class", "source", "found_at", "expires") and v not in ("", None)]
    if verdicts:
        props += [{"name": f"mosca:verdict:{h}", "value": v} for h, v in verdicts.items()]
    return {"type": "cryptographic-asset", "bom-ref": f"urn:mosca:{a['asset_id']}", "name": a.get("name", a["asset_id"]),
            "cryptoProperties": {"assetType": "algorithm",
                                 "algorithmProperties": {"primitive": PRIMITIVE.get(alg.split(" ")[0], "unknown"),
                                                         "parameterSetIdentifier": str(a.get("key_bits") or ""),
                                                         "executionEnvironment": "software-plain-ram",
                                                         "cryptoFunctions": ["keygen", "sign", "verify"] if a.get("purpose") == "signature" else ["keygen", "encapsulate", "decapsulate"]},
                                 "oid": ""},
            "evidence": {"occurrences": [{"location": f"{a.get('host', '')}:{a.get('port', '')}".rstrip(":")}]},
            "properties": props + [{"name": "mosca:algorithm", "value": alg}]}


def build(assets: list[dict], verdicts_by_asset: dict[str, dict] | None = None) -> dict:
    return {"bomFormat": "CycloneDX", "specVersion": "1.6", "serialNumber": f"urn:uuid:{uuid.uuid4()}", "version": 1,
            "metadata": {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "tools": {"components": [{"type": "application", "name": "mosca", "version": "0.1"}]}},
            "components": [component(a, (verdicts_by_asset or {}).get(a["asset_id"])) for a in assets]}


def attach(run) -> None:
    """whycore run hook: CBOM of the signals in this run with their verdicts."""
    assets, verd = [], {}
    for r in run.results:
        p = r["signal"]["props"]; assets.append(p)
        verd[p["asset_id"]] = {v["hypothesis_id"]: v["verdict"] for v in r["verdicts"]}
    run.extras["cbom"] = build(assets, verd)


if __name__ == "__main__":
    from whycore.data import data
    rows = data.run_sql("SELECT * FROM assets")["rows"]
    json.dump(build(rows), sys.stdout, indent=1, default=str)
