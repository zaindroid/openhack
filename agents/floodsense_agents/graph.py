"""Planned LangGraph topology. Not compiled.

Watchers (fast lane) → Investigator (deep) → Skeptic (at most 3 SQL
counter-checks, then a revise edge) → Exposure (deterministic SQL) →
Playbook (deep) → Judge → HITL interrupt.

Owners: Zain (graph, HITL, Judge with Mihir), Ayush (Nightshift, memory,
World Model). Every claim carries a citation record. Agents run reads
through Zetaris only.
"""

from __future__ import annotations

PLANNED_NODES: tuple[str, ...] = (
    "watchers",
    "investigator",
    "skeptic",
    "exposure",
    "playbook",
    "judge",
    "hitl",
)


def build_graph() -> None:
    """TODO: compile a LangGraph StateGraph with a checkpointer for HITL resume."""
    raise NotImplementedError(
        "LangGraph graph is a skeleton. See docs/GAMEPLAN.md (v0.2.0–v0.10.0)."
    )
