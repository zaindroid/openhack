"""Mosca's own endpoints (whycore includes `router` from app/routes.py, behind the same login).

GET  /whatif?z=YEAR     the latest run's assets judged again with Q-day moved to YEAR (the earlier anchor moves with it,
                        keeping the algorithms.yaml gap). Same tests (MoscaDomain._test), same evidence (the run's rows);
                        nothing is queried, stored or signed: a what-if, not a run.
POST /proof             {run_id, action_id}: after a human approved an action, handshake its asset again (TLS: openssl
                        s_client; SSH: the server's KEXINIT, no login), compare with the run's evidence and sign
                        before / approval / after with the notary (ML-DSA). Only assets in that run's inventory, which
                        only ever holds targets.yaml scans. Stored in MEMORY_DIR/proofs/proofs.jsonl.
GET  /proofs            proofs, newest first (?asset=ID for one asset)
GET  /proofs/{id}       one proof with its attestation, as a download"""
from __future__ import annotations
import json, os, re, sys, threading, time
from types import SimpleNamespace
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from whycore import events
from whycore.memory import memory
from whycore.settings import settings
from app import domain as M
from app import notary

router = APIRouter()
STATUS = {"LATE": "late", "AT RISK": "risk", "DEAD (retire)": "retire", "SAFE": "safe"}
GAP = M.Z[M.PRIMARY] - M.Z[M.EARLIEST]


def _runs() -> dict:
    import whycore.app as core          # loaded by then: whycore.app includes this router at the end of its import
    return core.RUNS


def _latest():
    done = [r for r in _runs().values() if r.results and r.status == "done"]
    return max(done, key=lambda r: r.created) if done else None


@router.get("/whatif")
def whatif(z: int):
    if not M.YEAR < z <= M.YEAR + 40:
        raise HTTPException(400, f"z must be a year after {M.YEAR}")
    run = _latest()
    if not run:
        raise HTTPException(404, "no finished run yet")
    hyps = M.DOMAIN.hypotheses(None, None)
    assets, counts = {}, {v: 0 for v in STATUS.values()}
    for r in run.results:
        p = r["signal"]["props"]
        vs = [M.DOMAIN._test(p, h, None, 0, zp=z, ze=z - GAP) for h in hyps]
        st = STATUS[M.DOMAIN.status_of(vs)]
        was = STATUS[M.DOMAIN.status_of([SimpleNamespace(**v) for v in r["verdicts"]])]
        counts[st] += 1
        assets[p["asset_id"]] = {"st": st, "was": was, "start_by": round(z - float(p["x"]) - float(p["y"]), 2)}
    return {"run_id": run.id, "z": z, "earliest": z - GAP, "year": M.YEAR, "run_anchors": {"primary": M.Z[M.PRIMARY], "earliest": M.Z[M.EARLIEST]},
            "counts": counts, "flipped": sum(a["st"] != a["was"] for a in assets.values()), "assets": assets,
            "note": "what-if over the run's evidence; not a run, not signed"}


# ---- proof after Approve -----------------------------------------------------------------------------------------
SCANNERS = os.path.join(os.path.dirname(__file__), "data", "scanners")
PROOFS = os.path.join(settings.memory_dir, "proofs", "proofs.jsonl")
_lock = threading.Lock()


class ProofReq(BaseModel):
    run_id: str
    action_id: str


def _scanner(name: str):
    if SCANNERS not in sys.path:
        sys.path.insert(0, SCANNERS)
    import importlib
    return importlib.import_module(name)


def _observe(p: dict) -> dict:
    """One handshake now, the same way the scanners made the inventory row."""
    m = re.search(r"connect ([^\s;]+):(\d+)", str(p.get("note") or ""))       # origin rows: dialled IP, SNI in host
    host, port = (m.group(1), int(m.group(2))) if m else (p["host"], int(p["port"]))
    if p["kind"] == "tls":
        tls = _scanner("scan_tls")
        info = tls.cert_info(host, port, p["host"], None)
        hs = tls.openssl_handshake(host, port, p["host"], None)
        return {"kex": hs["group"], "sig": f"{info['cert_alg']}-{info['bits']} cert" + (f", {hs['sig']}" if hs["sig"] else ""),
                "expires": info["expires"], "how": f"openssl s_client -connect {host}:{port} -servername {p['host']} -groups X25519MLKEM768:X25519:secp256r1"}
    if p["kind"] == "ssh":
        ssh = _scanner("scan_ssh")
        banner, kex, hk = ssh.server_kexinit(host, port)
        pq = [k for k in kex if k in ssh.PQ]
        return {"kex": pq[0] if pq else (kex[0] if kex else "none offered"), "sig": ",".join(hk), "banner": banner,
                "how": f"SSH KEXINIT from {host}:{port} (no user name, no login)"}
    raise HTTPException(400, f"no live check for kind {p['kind']}; proofs cover TLS and SSH endpoints")


def _store(proof: dict) -> None:
    with _lock:
        os.makedirs(os.path.dirname(PROOFS), exist_ok=True)
        with open(PROOFS, "a") as f:
            f.write(json.dumps(proof, default=str) + "\n")


def _proofs() -> list[dict]:
    if not os.path.exists(PROOFS):
        return []
    with open(PROOFS) as f:
        return [json.loads(ln) for ln in f if ln.strip()]


@router.post("/proof")
def proof(body: ProofReq):
    run = _runs().get(body.run_id)
    if not run:
        raise HTTPException(404, "no such run")
    r, a = next(((r, a) for r in run.results for a in r["actions"] if a["id"] == body.action_id), (None, None))
    if not a:
        raise HTTPException(404, "no such action in this run")
    if a["status"] != "approved":
        raise HTTPException(409, "a proof follows an approval; this action is " + a["status"])
    p, sid = r["signal"]["props"], r["signal"]["id"]
    try:
        after = _observe(p)
    except HTTPException:
        raise
    except Exception as e:
        after = {"kex": f"no handshake: {type(e).__name__}", "sig": "", "how": str(e)[:160]}
    pq_b = M._is_pq(p.get("negotiated_kex"), M.PQ_KEX)
    pq_a = M._is_pq(after["kex"], M.PQ_KEX)
    reached = not after["kex"].startswith("no handshake")
    outcome = "unreachable" if not reached else "fixed" if pq_a and not pq_b else "already" if pq_a else "regressed" if pq_b else "not yet"
    say = {"unreachable": f"could not handshake now ({after['kex'][14:]}); nothing proven either way","fixed": f"now negotiates {after['kex']} (was {p.get('negotiated_kex')})",
           "already": f"still post-quantum: {after['kex']}",
           "regressed": f"lost the post-quantum group: {after['kex']} (was {p.get('negotiated_kex')})",
           "not yet": f"still classical: {after['kex']}; the approved change is not live on this endpoint yet"}[outcome]
    d = memory.decision(a["id"], a["label"]) or {}
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    claims = [
        {"id": "before", "kind": "evidence", "status": "recorded", "rows": 1,
         "text": f"{sid} in run {run.id}: kex {p.get('negotiated_kex')}; sig {p.get('negotiated_sig')}",
         "source": f"{p.get('source')} inventory row, found {p.get('found_at')}"},
        {"id": "approval", "kind": "decision", "status": "approved",
         "text": f"{a['id']}: {a['label']} approved by a human" + (f" at {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(d['t']))}" if d.get("t") else ""),
         "source": "memory decisions.json, run " + str(d.get("run_id") or run.id)},
        {"id": "after", "kind": "handshake", "status": "observed", "rows": 1,
         "text": f"kex {after['kex']}; sig {after.get('sig', '')}", "source": f"{after['how']} at {now}"},
        {"id": "outcome", "kind": "proof", "status": outcome, "text": say},
    ]
    pid = f"proof-{sid}-{int(time.time())}"
    out = {"id": pid, "time": now, "run_id": run.id, "asset_id": sid, "asset": p.get("name"), "action_id": a["id"],
           "action": a["label"], "approved_at": d.get("t"), "applied": a.get("applied"), "outcome": outcome, "message": say,
           "before": {"kex": p.get("negotiated_kex"), "sig": p.get("negotiated_sig"), "found_at": p.get("found_at")},
           "after": after, "attestation": notary.attest(pid, claims)}
    _store(out)
    events.publish("proof", run_id=run.id, signal=sid, action=a["id"], outcome=outcome, proof_id=pid, message=say)
    return out


@router.get("/proofs")
def proofs(asset: str | None = None):
    xs = [x for x in _proofs() if not asset or x["asset_id"] == asset]
    return [{k: v for k, v in x.items() if k != "attestation"} | {"algorithm": x["attestation"]["algorithm"], "chain_root": x["attestation"]["chain_root"]}
            for x in reversed(xs)][:50]


@router.get("/proofs/{pid}")
def proof_file(pid: str):
    x = next((x for x in _proofs() if x["id"] == pid), None)
    if not x:
        raise HTTPException(404, "no such proof")
    return JSONResponse(x, headers={"Content-Disposition": f'attachment; filename="{pid}.json"'})
