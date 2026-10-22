"""Placeholder behaviour for the agent skeleton. No network, no LangGraph."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from floodsense_agents.graph import PLANNED_NODES, build_graph  # noqa: E402
from floodsense_agents.hitl import approval_status  # noqa: E402
from floodsense_agents.nodes.investigator import run as investigate  # noqa: E402
from floodsense_agents.nodes.judge import run as judge  # noqa: E402
from floodsense_agents.nodes.skeptic import run as challenge  # noqa: E402


class PlaceholderTest(unittest.TestCase):
    def test_planned_nodes_include_the_core_roles(self) -> None:
        self.assertIn("investigator", PLANNED_NODES)
        self.assertIn("skeptic", PLANNED_NODES)
        self.assertIn("judge", PLANNED_NODES)
        self.assertIn("hitl", PLANNED_NODES)

    def test_nodes_are_explicit_todos(self) -> None:
        state = {"run_id": "r-test"}
        self.assertEqual(investigate(state)["status"], "todo")
        self.assertEqual(challenge(state)["status"], "todo")
        self.assertEqual(judge(state)["scores"], [])
        self.assertIsNone(approval_status(state)["decision"])

    def test_graph_is_not_compiled(self) -> None:
        with self.assertRaises(NotImplementedError):
            build_graph()


if __name__ == "__main__":
    unittest.main()
