"""Skeptic node.

Owner: Zain, with Ayush.

TODO: try to disprove each causal link with at most three SQL counter-checks
against Zetaris. Mark a link supported or not supported. Stop after three
rounds. A planted false link should come back as not supported.
"""

from __future__ import annotations

from typing import Any


def run(state: dict[str, Any]) -> dict[str, Any]:
    """Placeholder. Does not query Zetaris."""
    return {
        "node": "skeptic",
        "status": "todo",
        "rounds": 0,
        "run_id": state.get("run_id"),
        "detail": "Skeptic loop is not implemented yet.",
    }
