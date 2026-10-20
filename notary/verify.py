#!/usr/bin/env python3
"""Verify a Mosca attestation offline.   python notary/verify.py <attestation.json>

Re-computes the SHA-256 chain over the embedded claims, checks it equals chain_root, and verifies the ML-DSA signature
over chain_root || run_id with the embedded public key. Needs only `pip install dilithium-py`.
Exit 0 = verified, 1 = tampered or invalid."""
from __future__ import annotations
import hashlib, json, sys


def canonical(claim: dict) -> bytes:
    keep = {k: claim.get(k) for k in ("id", "text", "kind", "sql", "source", "rows", "status")}
    return json.dumps(keep, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def main(path: str) -> int:
    att = json.load(open(path))
    h = hashlib.sha256(att["run_id"].encode()).hexdigest()
    for i, c in enumerate(att["claims_data"]):
        h = hashlib.sha256(bytes.fromhex(h) + canonical(c)).hexdigest()
        if att["claim_hashes"][i] != h:
            print(f"FAIL: claim {i} ({c.get('id')}) hash mismatch — content altered"); return 1
    if h != att["chain_root"]:
        print("FAIL: chain root mismatch"); return 1
    from dilithium_py.ml_dsa import ML_DSA_44, ML_DSA_65
    impl = {"ML-DSA-44": ML_DSA_44, "ML-DSA-65": ML_DSA_65}[att["algorithm"]]
    msg = bytes.fromhex(att["chain_root"]) + att["run_id"].encode()
    ok = impl.verify(bytes.fromhex(att["public_key"]), msg, bytes.fromhex(att["signature"]))
    print(("VERIFIED" if ok else "FAIL: bad signature") + f" — {att['algorithm']} by {att['signer']}, {att['claims']} claims, root {att['chain_root'][:16]}…, {att['time']}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
