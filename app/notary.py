"""Notary — ML-DSA-signed attestation of a run (run hook: RUN_HOOKS=app.notary:sign_run).

Chain: h0 = sha256(run_id) ; h_i = sha256(h_{i-1} || canonical(claim_i)) ; root = h_n.
The signer signs `root || run_id` with ML-DSA (FIPS 204). Three signers share one protocol:
  SoftSigner    — dilithium-py ML-DSA-65 on the host; key generated once under MEMORY_DIR/notary/ (demo + CI)
  SerialSigner  — the nRF5340 holding an ML-DSA-44 key (notary/nrf5340); host sends "SIGN <hex>", board answers "SIG <hex>"
  HttpSigner    — the same board on another machine: notary/serve.py next to it exposes GET /pub and POST /sign
                  (bearer NOTARY_TOKEN), reached over Tailscale at NOTARY_URL
`notary/verify.py` re-computes the chain from the attestation and verifies the signature offline.
Precedence: NOTARY_URL, then NOTARY_SERIAL, else the software signer. If the hardware signer cannot be reached when a
run is signed, the software signer signs instead and the attestation's signer field says why."""
from __future__ import annotations
import hashlib, json, os, time
from whycore.settings import settings

ALG_NAME = {44: "ML-DSA-44", 65: "ML-DSA-65"}


def canonical(claim: dict) -> bytes:
    keep = {k: claim.get(k) for k in ("id", "text", "kind", "sql", "source", "rows", "status")}
    if claim.get("sql_executed") is not None:          # the statement that ran (attestations before it lack the field)
        keep["sql_executed"] = claim["sql_executed"]
    return json.dumps(keep, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def chain(run_id: str, claims: list[dict]) -> tuple[str, list[str]]:
    h = hashlib.sha256(run_id.encode()).hexdigest()
    hashes = []
    for c in claims:
        h = hashlib.sha256(bytes.fromhex(h) + canonical(c)).hexdigest()
        hashes.append(h)
    return h, hashes


class SoftSigner:
    name = "software (host)"
    level = 65

    def __init__(self, key_dir: str) -> None:
        from dilithium_py.ml_dsa import ML_DSA_65
        self.impl = ML_DSA_65
        os.makedirs(key_dir, exist_ok=True)
        path = os.path.join(key_dir, "ml_dsa_65.json")
        if os.path.exists(path):
            js = json.load(open(path)); self.pk, self.sk = bytes.fromhex(js["pk"]), bytes.fromhex(js["sk"])
        else:
            self.pk, self.sk = self.impl.keygen()
            json.dump({"pk": self.pk.hex(), "sk": self.sk.hex(), "alg": ALG_NAME[65]}, open(path, "w"))

    def sign(self, msg: bytes) -> bytes:
        return self.impl.sign(self.sk, msg)


class SerialSigner:
    name = "nRF5340 (hardware)"
    level = 44

    def __init__(self, port: str) -> None:
        import serial  # pyserial
        self.ser = serial.Serial(port, 115200, timeout=20)
        self.ser.write(b"PUB\n"); line = self.ser.readline().decode().strip()
        if not line.startswith("PUB "):
            raise RuntimeError(f"unexpected board reply: {line[:60]}")
        self.pk = bytes.fromhex(line[4:])

    def sign(self, msg: bytes) -> bytes:
        self.ser.write(b"SIGN " + msg.hex().encode() + b"\n")
        line = self.ser.readline().decode().strip()
        if not line.startswith("SIG "):
            raise RuntimeError(f"board did not sign: {line[:60]}")
        return bytes.fromhex(line[4:])


class HttpSigner:
    """ML-DSA signer behind notary/serve.py (the board stays on the machine it is plugged into)."""

    def __init__(self, url: str, token: str) -> None:
        import httpx
        self.url, self.headers = url.rstrip("/"), {"Authorization": f"Bearer {token}"}
        r = httpx.get(self.url + "/pub", headers=self.headers, timeout=10)
        r.raise_for_status()
        js = r.json()
        self.pk = bytes.fromhex(js["public_key"])
        self.level = {v: k for k, v in ALG_NAME.items()}[js["algorithm"]]
        self.name = f"{js['signer']} via {self.url}"

    def sign(self, msg: bytes) -> bytes:
        import httpx
        r = httpx.post(self.url + "/sign", json={"msg": msg.hex()}, headers=self.headers, timeout=60)
        r.raise_for_status()
        return bytes.fromhex(r.json()["signature"])


_signer = None


def _soft() -> SoftSigner:
    return SoftSigner(os.path.join(settings.memory_dir, "notary"))


def get_signer():
    global _signer
    if _signer is None:
        if os.environ.get("NOTARY_URL"):
            _signer = HttpSigner(os.environ["NOTARY_URL"], os.environ.get("NOTARY_TOKEN", ""))
        elif os.environ.get("NOTARY_SERIAL"):
            _signer = SerialSigner(os.environ["NOTARY_SERIAL"])
        else:
            _signer = _soft()
    return _signer


def attest(run_id: str, claims: list[dict]) -> dict:
    global _signer
    root, hashes = chain(run_id, claims)
    msg = bytes.fromhex(root) + run_id.encode()
    try:
        s = get_signer()
        sig = s.sign(msg)
    except Exception as e:   # hardware unreachable: sign anyway, in software, and say so in the attestation
        _signer = None
        s = _soft()
        s.name = f"software (host); hardware signer unavailable: {type(e).__name__}: {str(e)[:80]}"
        sig = s.sign(msg)
    return {"version": 1, "run_id": run_id, "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "algorithm": ALG_NAME[s.level], "signer": s.name, "public_key": s.pk.hex(), "chain_root": root, "claims": len(claims),
            "claim_hashes": hashes, "signature": sig.hex(),
            "claims_data": [{k: c.get(k) for k in ("id", "text", "kind", "sql", "sql_executed", "source", "rows", "status") if k != "sql_executed" or c.get(k) is not None} for c in claims]}


def sign_run(run) -> None:
    """whycore run hook."""
    run.extras["attestation"] = attest(run.id, run.ledger.to_dict()["claims"])


sign_run.after_approval = True     # re-signed after an approved change is executed, so the attestation covers it
