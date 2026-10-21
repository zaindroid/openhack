"""Evidence ledger. A claim without a query is 'unverified' by construction; nothing in the UI can hide that.
A claim cites the query as written (`sql`) and the statement that actually ran (`sql_executed`, see whycore.data)."""
from __future__ import annotations
import hashlib, time
from dataclasses import dataclass, field, asdict


@dataclass
class Claim:
    text: str
    kind: str                       # signal | hypothesis | test | action | explanation
    sql: str | None = None
    source: str | None = None
    rows: int = 0
    data: dict = field(default_factory=dict)
    status: str = "verified"        # verified | unverified | rejected | uncertain | supported
    id: str = ""
    sql_executed: str | None = None

    def __post_init__(self) -> None:
        if not self.sql and self.status == "verified":
            self.status = "unverified"
        self.id = hashlib.sha1(f"{self.text}|{self.sql}|{time.time_ns()}".encode()).hexdigest()[:10]


class Ledger:
    def __init__(self) -> None:
        self.claims: list[Claim] = []
        self.steps: list[dict] = []
        self.t0 = time.time()

    def add(self, claim: Claim) -> Claim:
        self.claims.append(claim)
        return claim

    def step(self, agent: str, what: str, **kw) -> None:
        self.steps.append({"t": round(time.time() - self.t0, 3), "agent": agent, "what": what, **kw})

    def provenance_pct(self) -> float:
        n = [c for c in self.claims if c.kind in ("signal", "test")]
        return round(100.0 * sum(1 for c in n if c.status != "unverified") / len(n), 1) if n else 100.0

    def to_dict(self) -> dict:
        return {"claims": [asdict(c) for c in self.claims], "steps": self.steps, "provenance_pct": self.provenance_pct()}
