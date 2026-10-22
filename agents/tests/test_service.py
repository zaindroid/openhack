"""Agents HTTP service against the API contract: start -> approval payload -> decision -> resume, over the fakes. No network."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("CHECKPOINTER", "memory")
os.environ.setdefault("ZETARIS_MODE", "fake")
os.environ.setdefault("LLM_MODE", "fake")

from fastapi.testclient import TestClient  # noqa: E402
from langgraph.checkpoint.memory import MemorySaver  # noqa: E402

from floodsense_agents import __main__ as service  # noqa: E402
from floodsense_agents.graph import build_graph  # noqa: E402
from floodsense_agents.nightshift import FakeNightshift  # noqa: E402
from floodsense_agents.runtime import Runtime  # noqa: E402
from floodsense_agents.state import Deps, NoMemory  # noqa: E402
from floodsense_agents.zetaris import FakeZetaris  # noqa: E402


class ServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        deps = Deps(zetaris=FakeZetaris(), llm=FakeNightshift(), memory=NoMemory())
        service.set_runtime(Runtime(graph=build_graph(deps, MemorySaver(), ff_judge=True), deps=deps))
        self.c = TestClient(service.app)

    def test_health_and_config(self) -> None:
        body = self.c.get("/health").json()
        self.assertEqual(body["service"], "floodsense-agents")
        self.assertEqual(body["graph"], "compiled")
        self.assertEqual(body["served_from"], "live")
        cfg = self.c.get("/config").json()
        self.assertIn("FF_HITL", cfg["flags"])
        self.assertIn("nemotron", cfg["lanes"]["deep"])

    def test_run_review_approve(self) -> None:
        r = self.c.post("/runs", json={"question": "Which sites are exposed?", "event_id": "EMSR773", "customer_id": "demo-insurer"})
        self.assertEqual(r.status_code, 201)
        run = r.json()
        self.assertEqual(run["status"], "awaiting_approval")
        self.assertEqual(run["approval"]["status"], "awaiting")
        self.assertEqual(run["served_from"], "live")
        self.assertIsNone(run["cached_at"])
        for k in ("run_id", "thread_id", "event_id", "customer_id", "replay_ts", "anomalies", "hypotheses", "exposure", "playbook", "judge", "approval", "trace"):
            self.assertIn(k, run)
        rid = run["run_id"]

        approval = self.c.get(f"/runs/{rid}/approval").json()
        self.assertEqual(approval["run_id"], rid)
        self.assertTrue(approval["claims"] and approval["judge_summary"]["passes"])

        cits = self.c.get(f"/runs/{rid}/citations").json()
        self.assertTrue(cits["citations"] and all(c["layer"] in ("a", "b", "c") for c in cits["citations"]))
        self.assertTrue(all(c["query_id"] in cits["evidence"] for c in cits["citations"] if c["layer"] == "a"))

        self.assertEqual(self.c.post(f"/runs/{rid}/approval", json={"action": "edit"}).status_code, 422)
        done = self.c.post(f"/runs/{rid}/approval", json={"action": "approve", "reviewer": "saleeta"}).json()
        self.assertEqual(done["status"], "approved")
        self.assertEqual(done["approval"]["decision"], "approve")

        self.assertEqual(self.c.post(f"/runs/{rid}/approval", json={"action": "approve"}).status_code, 409)
        self.assertEqual(self.c.get(f"/runs/{rid}/approval").status_code, 409)
        past = self.c.get("/runs/past").json()["runs"]
        self.assertEqual(past[0]["run_id"], rid)
        self.assertEqual(past[0]["approval"], "approved")
        self.assertEqual(self.c.get("/runs/nope").status_code, 404)
        self.assertEqual(self.c.post("/runs", json={"question": "x", "event_id": "EMSR000"}).status_code, 422)

    def test_events_stream_sends_trace_events_then_status(self) -> None:
        rid = self.c.post("/runs", json={"question": "q", "event_id": "EMSR773"}).json()["run_id"]
        with self.c.stream("GET", f"/runs/{rid}/events") as s:
            text = "".join(s.iter_text())
        self.assertIn("event: trace", text)
        self.assertIn('"node": "watchers"', text)
        self.assertIn('"status": "awaiting_approval"', text)


if __name__ == "__main__":
    unittest.main()
