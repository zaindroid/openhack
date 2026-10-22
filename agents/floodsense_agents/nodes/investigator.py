"""Investigator node (deep Nemotron lane).

Owner: Zain, with Ayush on the Nightshift client.

TODO: turn a question into a cited causal chain (rain → catchment → river →
site) using Zetaris views only. Every claim carries a citation record.
"""

from __future__ import annotations

from typing import Any


def run(state: dict[str, Any]) -> dict[str, Any]:
    """Placeholder. Does not call a model."""
    return {
        "node": "investigator",
        "status": "todo",
        "run_id": state.get("run_id"),
        "detail": "LangGraph investigator is not implemented yet.",
    }
