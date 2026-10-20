"""Notary — ML-DSA-signed attestation of a run (run hook: RUN_HOOKS=app.notary:sign_run).

Chain: h0 = sha256(run_id) ; h_i = sha256(h_{i-1} || canonical(claim_i)) ; root = h_n.
The signer signs `root || run_id` with ML-DSA (FIPS 204). Two signers share one protocol:
  SoftSigner    — dilithium-py ML-DSA-65 on the host; key generated once under MEMORY_DIR/notary/ (demo + CI)
  SerialSigner  — the nRF5340 holding an ML-DSA-44 key (notary/nrf5340); host sends "SIGN <hex>", board answers "SIG <hex>"
`notary/verify.py` re-computes the chain from the attestation and verifies the signature offline.
Set NOTARY_SERIAL=/dev/ttyACM0 to use the board; otherwise the software signer is used and the attestation says so."""
from __future__ import annotations
import hashlib, json, os, time
from whycore.settings import settings

ALG_NAME = {44: "ML-DSA-44", 65: "ML-DSA-65"}


def canonical(claim: dict) -> bytes:
    keep = {k: claim.get(k) for k in ("id", "text", "kind", "sql", "source", "rows", "status")}
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


_signer = None


def get_signer():
    global _signer
    if _signer is None:
        port = os.environ.get("NOTARY_SERIAL")
        _signer = SerialSigner(port) if port else SoftSigner(os.path.join(settings.memory_dir, "notary"))
    return _signer


def attest(run_id: str, claims: list[dict]) -> dict:
    s = get_signer()
    root, hashes = chain(run_id, claims)
    msg = bytes.fromhex(root) + run_id.encode()
    sig = s.sign(msg)
    return {"version": 1, "run_id": run_id, "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "algorithm": ALG_NAME[s.level], "signer": s.name, "public_key": s.pk.hex(), "chain_root": root, "claims": len(claims),
            "claim_hashes": hashes, "signature": sig.hex(),
            "claims_data": [{k: c.get(k) for k in ("id", "text", "kind", "sql", "source", "rows", "status")} for c in claims]}


def sign_run(run) -> None:
    """whycore run hook."""
    run.extras["attestation"] = attest(run.id, run.ledger.to_dict()["claims"])
