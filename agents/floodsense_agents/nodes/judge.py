"""LLM-as-a-Judge node.

Owners: Zain and Mihir.

TODO: score each claim for coverage, citation faithfulness, grounding,
numeric match, and licence before the human approval interrupt. The Judge
does not approve, delete, or silently rewrite a claim. See docs/GAMEPLAN.md.
"""

from __future__ import annotations

from typing import Any


def run(state: dict[str, Any]) -> dict[str, Any]:
    """Placeholder. Does not call Nightshift."""
    return {
        "node": "judge",
        "status": "todo",
        "scores": [],
        "run_id": state.get("run_id"),
        "detail": "LLM-as-a-Judge is not implemented yet.",
    }
