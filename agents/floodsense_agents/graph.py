"""The FloodSense LangGraph.

    watchers → investigator → skeptic ─┬─ not_supported & no revise yet → revise → investigator → skeptic
                                       └─ → exposure → playbook → judge ─┬─ flagged & repair left → playbook (repair) → judge
                                                                          └─ → hitl (interrupt) → END
FF_SKEPTIC=false skips the Skeptic, FF_JUDGE=false skips the Judge, FF_HITL=false auto-approves (dev only).

    graph = build_graph(deps, checkpointer)
    out = graph.invoke({"run_id": rid, "request": req, "event": event}, {"configurable": {"thread_id": rid}})
    out["__interrupt__"][0].value            # the approval payload; the run is paused
    graph.invoke(Command(resume={"action": "approve"}), config)

Owners: Zain (graph, HITL, Judge with Mihir), Ayush (Nightshift, memory, World Model). Agents read data through Zetaris only.
"""
from __future__ import annotations
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from floodsense_agents import hitl as hitl_mod
from floodsense_agents.nightshift import build_llm
from floodsense_agents.nodes import exposure, investigator, judge, playbook, skeptic, watchers
from floodsense_agents.settings import settings
from floodsense_agents.state import Deps, FloodState, NoMemory
from floodsense_agents.zetaris import build_zetaris

PLANNED_NODES: tuple[str, ...] = ("watchers", "investigator", "skeptic", "exposure", "playbook", "judge", "hitl")


def build_deps() -> Deps:
    return Deps(zetaris=build_zetaris(), llm=build_llm(), memory=NoMemory())


def build_graph(deps: Deps | None = None, checkpointer=None, *, ff_skeptic: bool | None = None, ff_judge: bool | None = None):
    deps = deps or build_deps()
    use_skeptic = settings.ff_skeptic if ff_skeptic is None else ff_skeptic
    use_judge = settings.ff_judge if ff_judge is None else ff_judge

    g = StateGraph(FloodState)
    g.add_node("watchers", watchers.make(deps))
    g.add_node("investigator", investigator.make(deps))
    g.add_node("exposure", exposure.make(deps))
    g.add_node("playbook", playbook.make(deps))
    g.add_node("hitl", hitl_mod.hitl)
    g.add_edge(START, "watchers")
    g.add_edge("watchers", "investigator")

    if use_skeptic:
        g.add_node("skeptic", skeptic.make(deps))
        g.add_node("revise", skeptic.bump_revise)
        g.add_edge("investigator", "skeptic")
        g.add_conditional_edges("skeptic", skeptic.route_after_skeptic, {"revise": "revise", "exposure": "exposure"})
        g.add_edge("revise", "investigator")
    else:
        g.add_edge("investigator", "exposure")
    g.add_edge("exposure", "playbook")

    if use_judge:
        g.add_node("judge", judge.make(deps))
        g.add_edge("playbook", "judge")
        g.add_conditional_edges("judge", judge.route_after_judge, {"repair": "playbook", "hitl": "hitl"})
    else:
        g.add_edge("playbook", "hitl")
    g.add_edge("hitl", END)
    return g.compile(checkpointer=checkpointer or MemorySaver())
