"""Run lifecycle on top of the compiled graph: start (runs until the HITL interrupt), snapshot, resume with a decision.
Used by the agents service (__main__.py) and by the eval runner. The API container proxies these calls (api/app/main.py)."""
from __future__ import annotations
import logging, uuid
from typing import Any
from langgraph.types import Command
from floodsense_agents.checkpoints import build_checkpointer
from floodsense_agents.events import spec
from floodsense_agents.graph import build_deps, build_graph
from floodsense_agents.hitl import approval_payload
from floodsense_agents.models import ApprovalDecision, RunRequest
from floodsense_agents.zetaris import now_utc

log = logging.getLogger("floodsense.runtime")
STATE_KEYS = ("run_id", "thread_id", "event_id", "customer_id", "replay_ts", "anomalies", "hypotheses", "exposure", "playbook", "judge", "approval", "trace",
              "request", "event", "claims", "summary", "judge_summary", "evidence", "provenance", "revise_rounds", "repair_rounds", "model_ids", "error")


class RunNotFound(KeyError):
    pass


class NotAwaitingApproval(RuntimeError):
    pass


class Runtime:
    def __init__(self, graph=None, deps=None) -> None:
        self.deps = deps if deps is not None else (None if graph is not None else build_deps())
        self.graph = graph if graph is not None else build_graph(self.deps, build_checkpointer())
        self.index: dict[str, dict[str, Any]] = {}          # run_id -> row for /runs/past (this process; state lives in the checkpointer)

    @staticmethod
    def cfg(run_id: str) -> dict:
        return {"configurable": {"thread_id": run_id}}

    def snapshot(self, run_id: str) -> dict[str, Any]:
        snap = self.graph.get_state(self.cfg(run_id))
        if not snap or not snap.values:
            raise RunNotFound(run_id)
        v = dict(snap.values)
        paused = bool(snap.tasks and any(getattr(t, "interrupts", None) for t in snap.tasks))
        out = {k: v.get(k) for k in STATE_KEYS}
        for k, empty in (("anomalies", []), ("hypotheses", []), ("playbook", []), ("judge", []), ("trace", []), ("claims", []), ("model_ids", []),
                         ("evidence", {}), ("exposure", {}), ("provenance", [])):
            out[k] = out[k] if out[k] is not None else empty
        out["approval"] = out["approval"] or {"status": "awaiting" if paused else "not_reached", "decision": None, "edits": None, "reviewer_note": None}
        out["status"] = "awaiting_approval" if paused else v.get("status", "running")
        out["served_from"] = v.get("served_from", "live")
        out["cached_at"] = v.get("cached_at")
        return out

    def approval(self, run_id: str) -> dict[str, Any]:
        s = self.snapshot(run_id)
        if s["status"] != "awaiting_approval":
            raise NotAwaitingApproval(f"run {run_id} is {s['status']}")
        return approval_payload(s)

    def citations(self, run_id: str) -> dict[str, Any]:
        s = self.snapshot(run_id)
        cits = [c for claim in s["claims"] for c in claim.get("citations", [])]
        return {"run_id": run_id, "citations": cits, "evidence": s["evidence"], "provenance": s["provenance"], "served_from": s["served_from"], "cached_at": s["cached_at"]}

    def _index_row(self, run_id: str) -> None:
        s = self.snapshot(run_id)
        now = now_utc()
        row = self.index.get(run_id, {"run_id": run_id, "created_at": now})
        row.update(status=s["status"], question=(s.get("request") or {}).get("question"), event_id=s.get("event_id"), customer_id=s.get("customer_id"),
                   replay_ts=s.get("replay_ts"), updated_at=now, judge_overall=(s.get("judge_summary") or {}).get("overall"),
                   approval=(s.get("approval") or {}).get("status"), served_from=s["served_from"], cached_at=s["cached_at"])
        self.index[run_id] = row

    def start(self, req: RunRequest) -> dict[str, Any]:
        run_id = uuid.uuid4().hex[:12]
        ev = spec(req.event_id)
        try:
            self.graph.invoke({"run_id": run_id, "thread_id": run_id, "event_id": ev.event_id, "customer_id": req.customer_id, "replay_ts": req.replay_ts,
                               "request": req.model_dump(), "event": ev.as_dict(), "served_from": "live", "cached_at": None, "trace": [],
                               "revise_rounds": 0, "repair_rounds": 0, "model_ids": []}, self.cfg(run_id))
        except Exception as e:
            log.exception("run %s failed", run_id)
            self.graph.update_state(self.cfg(run_id), {"status": "failed", "error": str(e)[:500]})
        self._index_row(run_id)
        return self.snapshot(run_id)

    def resume(self, run_id: str, decision: ApprovalDecision) -> dict[str, Any]:
        s = self.snapshot(run_id)
        if s["status"] != "awaiting_approval":
            raise NotAwaitingApproval(f"run {run_id} is {s['status']}, not awaiting approval")
        self.graph.invoke(Command(resume=decision.model_dump()), self.cfg(run_id))
        out = self.snapshot(run_id)
        if out["status"] == "approved" and self.deps is not None:
            try:
                self.deps.memory.store(run_id, out["request"], out["claims"], out["approval"])     # H-MEM write-on-approval (Ayush)
            except Exception as e:
                log.warning("memory.store failed: %s", str(e)[:120])
        self._index_row(run_id)
        return out

    def past(self, limit: int = 50) -> list[dict[str, Any]]:
        return sorted(self.index.values(), key=lambda r: r["updated_at"], reverse=True)[:limit]
