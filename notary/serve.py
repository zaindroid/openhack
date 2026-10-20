#!/usr/bin/env python3
"""Notary bridge: runs on the machine the nRF5340 DK is plugged into and lets Mosca (on servingz) sign through it over
Tailscale. The private key never leaves the board.

  GET  /pub    -> {"algorithm": "ML-DSA-44", "public_key": hex, "signer": "nRF5340 (hardware)"}
  POST /sign   {"msg": hex} -> {"signature": hex}       (bearer NOTARY_TOKEN on both)
  GET  /healthz

Every signature from the board is verified against its public key before it is returned, so a garbled serial line
fails here instead of producing an attestation that fails later.

  pip install fastapi uvicorn pyserial dilithium-py
  NOTARY_TOKEN=<random> python notary/serve.py --serial COM5 --host 100.84.181.5 --port 8099      # Windows
  NOTARY_TOKEN=<random> python notary/serve.py --serial /dev/ttyACM0 --host <tailscale-ip>         # Linux/macOS
  NOTARY_TOKEN=<random> python notary/serve.py --simulate --host 127.0.0.1                         # no board: software
                                                                                                    # ML-DSA-44, labelled
On servingz set NOTARY_URL=http://<this machine's tailscale ip>:8099 and the same NOTARY_TOKEN."""
from __future__ import annotations
import argparse, hmac, json, os, threading

import uvicorn
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel


class Board:
    """Line protocol of notary/nrf5340: PUB -> 'PUB <hex>', SIGN <hex> -> 'SIG <hex>'."""

    def __init__(self, port: str) -> None:
        import serial
        self.ser = serial.Serial(port, 115200, timeout=20)
        self.lock = threading.Lock()
        self.name = "nRF5340 (hardware)"
        self.pk = bytes.fromhex(self._cmd(b"PUB", "PUB "))

    def _cmd(self, line: bytes, expect: str) -> str:
        with self.lock:
            self.ser.reset_input_buffer()
            self.ser.write(line + b"\n")
            reply = self.ser.readline().decode(errors="ignore").strip()
        if not reply.startswith(expect):
            raise RuntimeError(f"unexpected board reply: {reply[:60]!r}")
        return reply[len(expect):]

    def sign(self, msg: bytes) -> bytes:
        return bytes.fromhex(self._cmd(b"SIGN " + msg.hex().encode(), "SIG "))


class Simulated:
    """Software ML-DSA-44 with a key file, for testing the bridge without the board. Labelled, never 'hardware'."""

    def __init__(self, key_file: str) -> None:
        from dilithium_py.ml_dsa import ML_DSA_44
        self.impl, self.name = ML_DSA_44, "simulated board (software ML-DSA-44 in notary/serve.py --simulate)"
        if os.path.exists(key_file):
            js = json.load(open(key_file)); self.pk, self.sk = bytes.fromhex(js["pk"]), bytes.fromhex(js["sk"])
        else:
            self.pk, self.sk = self.impl.keygen()
            json.dump({"pk": self.pk.hex(), "sk": self.sk.hex()}, open(key_file, "w"))

    def sign(self, msg: bytes) -> bytes:
        return self.impl.sign(self.sk, msg)


class SignIn(BaseModel):
    msg: str


def build(signer, token: str) -> FastAPI:
    from dilithium_py.ml_dsa import ML_DSA_44
    app = FastAPI(title="Mosca notary bridge")

    def auth(authorization: str | None) -> None:
        if not token or not authorization or not hmac.compare_digest(authorization, f"Bearer {token}"):
            raise HTTPException(401, "bad or missing token")

    @app.get("/healthz")
    def healthz():
        return {"ok": True, "signer": signer.name}

    @app.get("/pub")
    def pub(authorization: str | None = Header(None)):
        auth(authorization)
        return {"algorithm": "ML-DSA-44", "public_key": signer.pk.hex(), "signer": signer.name}

    @app.post("/sign")
    def sign(body: SignIn, authorization: str | None = Header(None)):
        auth(authorization)
        msg = bytes.fromhex(body.msg)
        if len(msg) > 4096:
            raise HTTPException(413, "message too long (attestations sign a 32-byte root plus the run id)")
        try:
            sig = signer.sign(msg)
        except Exception as e:
            raise HTTPException(502, f"signer failed: {str(e)[:120]}")
        if not ML_DSA_44.verify(signer.pk, msg, sig):
            raise HTTPException(502, "signature from the signer does not verify; refusing to return it")
        return {"signature": sig.hex()}

    return app


def main() -> None:
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--serial", help="serial port of the nRF5340 (COM5, /dev/ttyACM0)")
    src.add_argument("--simulate", action="store_true", help="software ML-DSA-44 (labelled), for testing without the board")
    ap.add_argument("--key-file", default="notary_sim_key.json", help="--simulate only")
    ap.add_argument("--host", default="127.0.0.1", help="bind address: the Tailscale IP of this machine")
    ap.add_argument("--port", type=int, default=8099)
    a = ap.parse_args()
    token = os.environ.get("NOTARY_TOKEN", "")
    if len(token) < 24:
        raise SystemExit("set NOTARY_TOKEN (at least 24 characters) — the same value goes into servingz as NOTARY_TOKEN")
    signer = Simulated(a.key_file) if a.simulate else Board(a.serial)
    print(f"notary bridge: {signer.name}, pk {signer.pk.hex()[:16]}…, on {a.host}:{a.port}")
    uvicorn.run(build(signer, token), host=a.host, port=a.port)


if __name__ == "__main__":
    main()
