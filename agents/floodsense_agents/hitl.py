"""Human-in-the-loop placeholder.

Owner: Zain. Tests with Mihir.

TODO: pause the run with LangGraph interrupt(), persist state with a
checkpointer (SqliteSaver under /data/checkpoints), and resume on
POST /runs/{id}/approval. Approve, edit, and reject. No outbound action
without a human decision. The human sees the Judge scores and is the
final judge.
"""

from __future__ import annotations

from typing import Any


def approval_status(state: dict[str, Any]) -> dict[str, Any]:
    """Return a not-yet-implemented approval record. Does not pause a run."""
    return {
        "node": "hitl",
        "status": "todo",
        "decision": None,
        "detail": "HITL interrupt is not implemented yet.",
        "thread_id": state.get("thread_id"),
    }
