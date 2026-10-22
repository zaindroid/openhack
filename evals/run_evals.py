"""Evaluation runner (gameplan §11). Headline number: the hallucination rate, the share of claims their own citations do not
support, as scored by the Judge. Also citation coverage, numeric accuracy, Judge pass rate, Skeptic rejections, expected
tokens hit and forbidden figures found.

    python evals/run_evals.py                          # both events, current env (fakes when no credentials)
    python evals/run_evals.py --event EMSR773 --strict --out reports/evals.md

Targets (proposal, gameplan §11): hallucination <= 5 %, citation coverage 100 %, numeric accuracy 100 %.
--strict exits 1 when a target is missed, for CI. Owners: Saleeta and Urvashi (items), Zain and Mihir (metrics).
"""
from __future__ import annotations
import argparse, json, os, re, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agents"))
os.environ.setdefault("CHECKPOINTER", "memory")
os.environ.setdefault("FF_JUDGE", "true")

import yaml  # noqa: E402
from langgraph.checkpoint.memory import MemorySaver  # noqa: E402
from floodsense_agents.graph import build_deps, build_graph  # noqa: E402
from floodsense_agents.models import ApprovalDecision, RunRequest  # noqa: E402
from floodsense_agents.runtime import Runtime  # noqa: E402

HERE = Path(__file__).resolve().parent
EVENTS = {"EMSR773": "valencia_2024.yaml", "EMSR517": "ahr_2021.yaml"}
TARGETS = {"hallucination_rate": ("<=", 0.05), "citation_coverage": (">=", 1.0), "numeric_accuracy": (">=", 1.0)}


def mentions(text: str, token: str) -> bool:
    return re.search(rf"(?<![\w.,]){re.escape(token.lower())}(?![\w])", text.lower()) is not None


def run_item(rt: Runtime, spec: dict, item: dict) -> dict:
    t0 = time.time()
    req = RunRequest(question=item["question"], event_id=spec["event_id"], customer_id=spec.get("customer_id", "demo-insurer"), replay_ts=item.get("replay_ts"))
    s = rt.start(req)
    if s["status"] == "awaiting_approval":
        s = rt.resume(s["run_id"], ApprovalDecision(action="approve", reviewer="evals"))
    text = " ".join([s.get("summary") or ""] + [c["text"] for c in s["claims"]] + [a["text"] for a in s["playbook"]])
    js = s.get("judge_summary") or {}
    expect, forbid = item.get("expect", []), item.get("forbid", [])
    hits = [e for e in expect if mentions(text, e)]
    viol = [f for f in forbid if mentions(text, f)]
    return {"id": item["id"], "question": item["question"], "status": s["status"], "elapsed_s": round(time.time() - t0, 2), "n_claims": js.get("n_claims", 0),
            "hallucination_rate": js.get("hallucination_rate", 1.0), "citation_coverage": js.get("citation_coverage", 0.0),
            "numeric_accuracy": js.get("numeric_accuracy", 0.0), "judge_passes": js.get("passes", False), "judge_overall": js.get("overall", 0.0),
            "repair_rounds": s.get("repair_rounds", 0), "revise_rounds": s.get("revise_rounds", 0),
            "skeptic_rejections": sum(1 for h in s["hypotheses"] if h["status"] == "not_supported"),
            "expect_hits": f"{len(hits)}/{len(expect)}", "expect_hit_rate": (len(hits) / len(expect)) if expect else None,
            "forbid_violations": viol, "model_ids": sorted(set(s.get("model_ids", []))), "summary": s.get("summary", "")}


def aggregate(rows: list[dict]) -> dict:
    n = len(rows) or 1
    rated = [r["expect_hit_rate"] for r in rows if r["expect_hit_rate"] is not None]
    return {"items": len(rows), "hallucination_rate": round(sum(r["hallucination_rate"] for r in rows) / n, 4),
            "citation_coverage": round(sum(r["citation_coverage"] for r in rows) / n, 4), "numeric_accuracy": round(sum(r["numeric_accuracy"] for r in rows) / n, 4),
            "judge_pass_rate": round(sum(r["judge_passes"] for r in rows) / n, 4), "judge_overall": round(sum(r["judge_overall"] for r in rows) / n, 3),
            "expect_hit_rate": round(sum(rated) / len(rated), 4) if rated else None, "forbid_violations": sum(len(r["forbid_violations"]) for r in rows),
            "repair_rounds": sum(r["repair_rounds"] for r in rows), "skeptic_rejections": sum(r["skeptic_rejections"] for r in rows),
            "mean_elapsed_s": round(sum(r["elapsed_s"] for r in rows) / n, 2)}


def ok(a: dict) -> dict[str, bool]:
    return {k: (a[k] <= v if op == "<=" else a[k] >= v) for k, (op, v) in TARGETS.items()}


def markdown(results: dict) -> str:
    out = [f"# FloodSense evals — {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}", "",
           f"LLM `{results['llm']}` · Zetaris `{results['zetaris']}` · targets: hallucination ≤ 5 %, coverage 100 %, numeric 100 %", ""]
    for ev, block in results["events"].items():
        a, flags = block["aggregate"], ok(block["aggregate"])
        mark = lambda k: "✅" if flags[k] else "❌"  # noqa: E731
        out += [f"## {ev}", "",
                f"**hallucination {a['hallucination_rate']:.1%}** {mark('hallucination_rate')} · **coverage {a['citation_coverage']:.0%}** {mark('citation_coverage')} · "
                f"**numeric {a['numeric_accuracy']:.0%}** {mark('numeric_accuracy')} · judge pass {a['judge_pass_rate']:.0%} (overall {a['judge_overall']:.2f}) · "
                f"expected tokens {a['expect_hit_rate'] if a['expect_hit_rate'] is None else format(a['expect_hit_rate'], '.0%')} · forbidden figures {a['forbid_violations']} · "
                f"repairs {a['repair_rounds']} · skeptic rejections {a['skeptic_rejections']} · {a['mean_elapsed_s']} s/item", "",
                "| id | halluc. | coverage | numeric | claims | repairs | expected | forbidden | status |", "|---|---|---|---|---|---|---|---|---|"]
        for r in block["rows"]:
            out.append(f"| {r['id']} | {r['hallucination_rate']:.0%} | {r['citation_coverage']:.0%} | {r['numeric_accuracy']:.0%} | {r['n_claims']} | {r['repair_rounds']} | "
                       f"{r['expect_hits']} | {', '.join(r['forbid_violations']) or '—'} | {r['status']} |")
        out.append("")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--event", choices=list(EVENTS), action="append")
    ap.add_argument("--out", help="markdown report path (a .json twin is written beside it)")
    ap.add_argument("--strict", action="store_true", help="exit 1 when a target is missed")
    args = ap.parse_args(argv)
    deps = build_deps()
    rt = Runtime(graph=build_graph(deps, MemorySaver(), ff_judge=True), deps=deps)
    results = {"llm": type(deps.llm).__name__, "zetaris": type(deps.zetaris).__name__, "events": {}}
    for ev in args.event or list(EVENTS):
        spec = yaml.safe_load((HERE / EVENTS[ev]).read_text(encoding="utf-8"))
        rows = [run_item(rt, spec, item) for item in spec["items"]]
        results["events"][ev] = {"rows": rows, "aggregate": aggregate(rows)}
        a = results["events"][ev]["aggregate"]
        print(f"{ev}: hallucination={a['hallucination_rate']:.1%} coverage={a['citation_coverage']:.0%} numeric={a['numeric_accuracy']:.0%} "
              f"judge_pass={a['judge_pass_rate']:.0%} expect_hit={a['expect_hit_rate']} forbid={a['forbid_violations']} repairs={a['repair_rounds']}")
    md = markdown(results)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(md, encoding="utf-8")
        Path(args.out).with_suffix(".json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"report: {args.out}")
    missed = any(not all(ok(b["aggregate"]).values()) for b in results["events"].values())
    return 1 if (args.strict and missed) else 0


if __name__ == "__main__":
    sys.exit(main())
