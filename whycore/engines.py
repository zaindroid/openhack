"""Run hooks backed by the Meterless engines sidecar (whycore/meterless/server.ts, METERLESS_ENGINES_URL).

  whycore.engines:world_model   observe every signal of the run in the World Model (one entity per signal, its props and
                                the Skeptic's verdicts as facts with provenance). The sidecar returns what changed since
                                the previous observation (e.g. negotiated_kex X25519 -> X25519MLKEM768 after a fix);
                                stored in run.extras["world_model"] and logged as a ledger step.
  whycore.engines:brief         one run-wide brief written by the Markovian engine (goal: domain.brief_goal if set): the run's results go in as an
                                attachment, the model writes in bounded chunks with a carried-over state block instead
                                of one ever-growing prompt. Added to the ledger as an unverified explanation claim and
                                to run.extras["brief"] with the engine's token accounting.
Both hooks are no-ops (recorded as such) when the sidecar is not configured or not reachable."""
from __future__ import annotations
import time
from whycore.ledger import Claim
from whycore.model import model
from whycore.settings import settings

FACT_KEYS = ("kind", "algorithm", "key_bits", "negotiated_kex", "negotiated_sig", "expires", "in_use", "data_class", "purpose")


def _post(path: str, body: dict, timeout: float = 30) -> dict:
    import httpx
    if not settings.meterless_engines_url:
        raise RuntimeError("METERLESS_ENGINES_URL unset")
    r = httpx.post(settings.meterless_engines_url.rstrip("/") + path, json=body, timeout=timeout)
    r.raise_for_status()
    return r.json()


def world_model(run) -> None:
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    items = []
    for r in run.results:
        s, p = r["signal"], r["signal"]["props"]
        observed = str(p.get("found_at") or now)
        facts = {k: p[k] for k in FACT_KEYS if k in p and p[k] not in (None, "")}
        facts.update({f"verdict:{v['hypothesis_id']}": v["verdict"] for v in r["verdicts"]})
        items.append({"type": str(p.get("kind") or "signal"), "id": s["id"], "name": str(p.get("name") or s["label"])[:120],
                      "at": observed if "T" in observed else observed + "T00:00:00Z", "facts": facts})
    out = _post("/wm/observe", {"namespace": run.domain.name, "runId": run.id, "by": f"whycore:{settings.meterless_app}", "items": items})
    run.extras["world_model"] = out
    run.ledger.step("world_model", f"{out['entities']} entities, {out['facts']} facts, {len(out['changes'])} changes since last observation")


def brief(run) -> None:
    e = model.ep["reason"]
    if not (model.configured and e.base):
        raise RuntimeError("no model endpoint for the Markovian brief")
    lines = []
    for r in run.results:
        v = ", ".join(f"{x['hypothesis_id']}={x['verdict']}" for x in r["verdicts"])
        top = r["actions"][0]["label"] if r["actions"] else "none"
        lines.append(f"- {r['signal']['id']} | {r['signal']['label']} | {v} | first action: {top}")
    goal = getattr(run.domain, "brief_goal", None) or (
        f"{run.domain.question} Write a brief for a decision maker: for each signal say which hypotheses were supported, "
        "rejected or left uncertain, name the signal ids, and give the order of work from the first actions. "
        "Use only the facts in the attachment; never invent dates or numbers.")
    t0 = time.time()
    out = _post("/markovian/run", {"goal": goal, "attachments": [{"name": "results.txt", "content": "\n".join(lines)}],
                                    "chunkConfig": {"chunkSize": 3000, "maxChunks": 4, "carryoverTokens": 512},   # engine: chunkSize >= 400 framing + carryover + 1200 output
                                    "endpoint": {"base": e.base, "key": e.key, "model": e.model, "maxTokens": 700,
                                                 "thinkingOff": settings.model_thinking == "off" and e.route != "meterless",
                                                 "headers": {"meterless-app": settings.meterless_app, "meterless-scope": "user"}}},
                timeout=90)
    keep = {k: out.get(k) for k in ("id", "status", "chunkConfig", "totalTokensUsed", "totalTokensSaved", "efficiencyPercent",
                                    "tokenLabel", "durationMs", "measuredTokens", "error")}
    keep["chunks"] = len(out.get("chunks") or [])
    keep["output"] = out.get("output", "")
    keep["model"] = {"route": e.route, "host": e.host, "model": e.model}
    run.extras["brief"] = keep
    run.ledger.add(Claim(text=keep["output"], kind="explanation", status="unverified",
                         data={"engine": "markovian", "chunks": keep["chunks"], "status": keep["status"], **keep["model"]}))
    run.ledger.step("brief", f"markovian {keep['status']} in {keep['chunks']} chunks, {time.time() - t0:.1f}s")
