#!/usr/bin/env python3
"""Verify the QEMU self-test output with dilithium-py (independent FIPS 204 ML-DSA-44).
   python verify.py <qemu-output.txt>      (pip install dilithium-py)"""
import sys
from dilithium_py.ml_dsa import ML_DSA_44

vals = {}
for line in open(sys.argv[1], errors="replace"):
    parts = line.strip().split(" ", 1)
    if len(parts) == 2 and parts[0] in ("PK", "MSG", "SIG"):
        vals[parts[0]] = bytes.fromhex(parts[1])
pk, msg, sig = vals["PK"], vals["MSG"], vals["SIG"]
assert (len(pk), len(sig)) == (1312, 2420), (len(pk), len(sig))
ok = ML_DSA_44.verify(pk, msg, sig)
bad = ML_DSA_44.verify(pk, msg + b"x", sig)
print(f"dilithium-py ML-DSA-44 verify: {ok}; altered message: {bad}")
sys.exit(0 if ok and not bad else 1)
