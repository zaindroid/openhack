#!/usr/bin/env python3
"""Measure the Mosca notary board: on-device timings (TIME) and host round trips.

  pip install pyserial httpx dilithium-py
  python measure.py --serial COM5 [--gen] [--n 20]        # direct: PUB, n x SIGN, TIME, one 2048-byte SIGN
  NOTARY_TOKEN=... python measure.py --url http://127.0.0.1:8099 [--n 20]   # through notary/serve.py

Only one program can hold the COM port: run the --serial measurement before starting serve.py.
Every signature is verified with dilithium-py (FIPS 204 ML-DSA-44, empty context)."""
from __future__ import annotations
import argparse, os, statistics, sys, time

from dilithium_py.ml_dsa import ML_DSA_44

MSG_BYTES = 32 + 20  # an attestation signs chain_root (32 bytes) || run_id (~20 bytes)


def summary(name: str, xs: list[float]) -> str:
    return (f"{name}: n={len(xs)} median={statistics.median(xs):.1f} ms "
            f"min={min(xs):.1f} ms max={max(xs):.1f} ms")


def serial_mode(port: str, n: int, gen: bool) -> int:
    import serial
    ser = serial.Serial(port, 115200, timeout=30)

    def cmd(line: str) -> tuple[str, float]:
        ser.reset_input_buffer()
        t0 = time.perf_counter()
        ser.write(line.encode() + b"\n")
        reply = ser.readline().decode(errors="replace").strip()
        return reply, (time.perf_counter() - t0) * 1000

    reply, _ = cmd("PUB")
    if reply.startswith("ERR no key") and gen:
        reply, ms = cmd("GEN")
        print(f"GEN -> {reply} (round trip {ms:.0f} ms)")
        print("TIME ->", cmd("TIME")[0])
        reply, _ = cmd("PUB")
    if not reply.startswith("PUB "):
        print("board did not return a public key:", reply[:80]); return 1
    pk = bytes.fromhex(reply[4:])
    print(f"PUB ok, {len(pk)} bytes, {pk.hex()[:16]}...")

    rtts, bad = [], 0
    for i in range(n):
        msg = os.urandom(MSG_BYTES)
        reply, ms = cmd("SIGN " + msg.hex())
        if not reply.startswith("SIG ") or not ML_DSA_44.verify(pk, msg, bytes.fromhex(reply[4:])):
            bad += 1; print("bad reply:", reply[:80]); continue
        rtts.append(ms)
        if i == 0:
            print("TIME after first SIGN ->", cmd("TIME")[0])
    print(summary(f"SIGN {MSG_BYTES} B round trip (serial)", rtts))

    msg = os.urandom(2048)
    reply, ms = cmd("SIGN " + msg.hex())
    ok = reply.startswith("SIG ") and ML_DSA_44.verify(pk, msg, bytes.fromhex(reply[4:]))
    print(f"SIGN 2048 B: {'ok' if ok else 'FAILED ' + reply[:60]} round trip {ms:.0f} ms")
    print("TIME ->", cmd("TIME")[0])
    return 0 if ok and not bad else 1


def http_mode(url: str, n: int) -> int:
    import httpx
    h = {"Authorization": "Bearer " + os.environ.get("NOTARY_TOKEN", "")}
    js = httpx.get(url.rstrip("/") + "/pub", headers=h, timeout=10).raise_for_status().json()
    pk = bytes.fromhex(js["public_key"])
    print(f"/pub: {js['algorithm']} {js['signer']} {pk.hex()[:16]}...")
    rtts = []
    with httpx.Client(headers=h, timeout=60) as c:
        for _ in range(n):
            msg = os.urandom(MSG_BYTES)
            t0 = time.perf_counter()
            r = c.post(url.rstrip("/") + "/sign", json={"msg": msg.hex()}).raise_for_status()
            rtts.append((time.perf_counter() - t0) * 1000)
            assert ML_DSA_44.verify(pk, msg, bytes.fromhex(r.json()["signature"]))
    print(summary(f"POST /sign {MSG_BYTES} B round trip (HTTP via serve.py)", rtts))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--serial", help="COM5 / /dev/ttyACM0")
    src.add_argument("--url", help="notary/serve.py base URL, e.g. http://127.0.0.1:8099")
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--gen", action="store_true", help="send GEN first if the board has no key")
    a = ap.parse_args()
    return serial_mode(a.serial, a.n, a.gen) if a.serial else http_mode(a.url, a.n)


if __name__ == "__main__":
    sys.exit(main())
