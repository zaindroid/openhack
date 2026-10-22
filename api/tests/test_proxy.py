"""API proxies the run lifecycle to the agents service. The agents app is mounted in-process through httpx's transport,
so this test needs no network and no second process."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "agents"))
os.environ.setdefault("CHECKPOINTER", "memory")
os.environ.setdefault("ZETARIS_MODE", "fake")
os.environ.setdefault("LLM_MODE", "fake")

import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import main as api  # noqa: E402

try:
    from floodsense_agents import __main__ as agents_service  # noqa: E402
except ImportError:  # the agents requirements are not installed here; the health test still covers the API
    agents_service = None


@unittest.skipIf(agents_service is None, "agents package not importable")
class ProxyTest(unittest.TestCase):
    def setUp(self) -> None:
        from langgraph.checkpoint.memory import MemorySaver
        from floodsense_agents.graph import build_graph
        from floodsense_agents.nightshift import FakeNightshift
        from floodsense_agents.runtime import Runtime
        from floodsense_agents.state import Deps, NoMemory
        from floodsense_agents.zetaris import FakeZetaris

        deps = Deps(zetaris=FakeZetaris(), llm=FakeNightshift(), memory=NoMemory())
        agents_service.set_runtime(Runtime(graph=build_graph(deps, MemorySaver(), ff_judge=True), deps=deps))
        inner = TestClient(agents_service.app)

        def fake_request(method, url, **kw):      # route the proxy's outbound calls into the in-process agents app
            path = url.replace(api.AGENTS_URL, "")
            return inner.request(method, path, json=kw.get("json"), params=kw.get("params"))

        self._patch = mock.patch.object(api.httpx, "request", side_effect=fake_request)
        self._patch.start()
        self.addCleanup(self._patch.stop)
        self.c = TestClient(api.app)

    def test_start_approve_through_the_api(self) -> None:
        r = self.c.post("/runs", json={"question": "Which sites are exposed?", "event_id": "EMSR773"})
        self.assertEqual(r.status_code, 201)
        run = r.json()
        self.assertEqual(run["status"], "awaiting_approval")
        self.assertEqual(run["served_from"], "live")
        rid = run["run_id"]
        self.assertEqual(self.c.get(f"/runs/{rid}/approval").status_code, 200)
        done = self.c.post(f"/runs/{rid}/approval", json={"action": "approve", "reviewer": "zain"}).json()
        self.assertEqual(done["status"], "approved")
        self.assertEqual(self.c.get(f"/runs/{rid}/citations").status_code, 200)
        self.assertEqual(self.c.get("/runs/past").json()["runs"][0]["run_id"], rid)
        self.assertEqual(self.c.get("/config").json()["lanes"]["fast"].split("/")[0], "nvidia")

    def test_agents_down_is_a_503(self) -> None:
        self._patch.stop()
        with mock.patch.object(api.httpx, "request", side_effect=httpx.ConnectError("refused")):
            self.assertEqual(self.c.get("/runs/past").status_code, 503)
        self._patch.start()


if __name__ == "__main__":
    unittest.main()
