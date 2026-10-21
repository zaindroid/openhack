"""The contract every idea implements in app/domain.py. Keep domain code about the DOMAIN (what a signal is, which
causes compete, what test rejects a cause, what action follows); the loop, ledger, memory, UI and model wiring are
whycore's."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from whycore.data import DataAccess


@dataclass
class Signal:
    id: str
    label: str
    score: float                         # higher = more urgent; drives ordering
    props: dict = field(default_factory=dict)   # free-form; lat/lon shown on the map when present
    sql: str | None = None
    rows: int = 0
    sql_executed: str | None = None      # set by the pipeline from whycore.data unless the domain sets it


@dataclass
class Hypothesis:
    id: str
    label: str
    props: dict = field(default_factory=dict)


@dataclass
class TestResult:
    hypothesis_id: str
    verdict: str                         # support | reject | uncertain
    reason: str                          # one plain sentence, numbers inside
    sql: str | None = None
    rows: int = 0
    data: dict = field(default_factory=dict)
    sql_executed: str | None = None      # set by the pipeline from whycore.data unless the domain sets it


@dataclass
class Action:
    id: str
    label: str
    priority: int                        # 1 = first
    rationale: str
    props: dict = field(default_factory=dict)
    status: str = "draft"                # draft | approved | rejected


class Domain:
    """Subclass this. Only scout/hypotheses/test/plan are required."""
    name = "domain"
    title = "Untitled domain"
    track = "03"
    question = "What is happening, why, and what do we do first?"
    description = ""
    views: dict[str, str] = {}           # name -> SQL for the UI's data tabs (optional)
    sources: list[dict] = []             # [{name, url, access, status}] for the UI's sources tab

    def scout(self, data: DataAccess, limit: int) -> list[Signal]:
        raise NotImplementedError

    def hypotheses(self, signal: Signal, data: DataAccess) -> list[Hypothesis]:
        raise NotImplementedError

    def test(self, signal: Signal, hyp: Hypothesis, data: DataAccess) -> TestResult:
        raise NotImplementedError

    def plan(self, signal: Signal, verdicts: list[TestResult], data: DataAccess) -> list[Action]:
        raise NotImplementedError

    def explain_prompt(self, signal: Signal, verdicts: list[TestResult], actions: list[Action]) -> tuple[str, str]:
        """(system, user) for the model. Default: a plain summary; domains may override for better prose."""
        sys_ = (f"You are the explainer for {self.title}. Explain the verdicts below to a decision-maker in plain language, "
                "in at most 120 words. Do not add facts that are not in the input. Every number you mention must appear in the input.")
        lines = [f"Signal: {signal.label} (score {signal.score})"]
        for v in verdicts:
            lines.append(f"- {v.hypothesis_id}: {v.verdict.upper()} — {v.reason}")
        lines.append("Actions (drafts): " + "; ".join(f"{a.priority}. {a.label}" for a in actions))
        return sys_, "\n".join(lines)

    def extra_json(self, data: DataAccess) -> dict[str, Any]:
        """Anything the UI should show for this domain (e.g. a map centre). Optional."""
        return {}
