"""Eval runner shared by every idea: python -m whycore.evals [app/evals.yaml] [--keep-memory]

cases:
  - id: salt_veendam
    signal_contains: "Veendam"            # a signal whose label contains this must exist
    expect_supported: [salt]              # hypothesis ids that must be supported for that signal
    expect_rejected: [gas]                # hypothesis ids that must be rejected
    first_action_contains: "dike"         # the top action's label must contain this (optional)
  - id: warm_run
    warm: true                            # run twice; second run must skip ≥1 hypothesis via memory AND reach the
                                          # same verdict for every signal (memory may save work, never change answers)
Scores: pass/fail per case, provenance %, tests cold vs warm.
"""
from __future__ import annotations
import importlib, json, os, sys
import yaml
from whycore.memory import memory
from whycore.pipeline import Run


def _find(run: Run, needle: str) -> dict | None:
    for r in run.results:
        if needle.lower() in r["signal"]["label"].lower():
            return r
    return None


def main(argv: list[str]) -> int:
    path = next((a for a in argv if a.endswith((".yaml", ".yml"))), "app/evals.yaml")
    keep = "--keep-memory" in argv
    domain = importlib.import_module(os.environ.get("DOMAIN_MODULE", "app.domain")).DOMAIN
    cases = yaml.safe_load(open(path))["cases"]
    if not keep:
        memory.reset()
    passed, report = 0, []
    base = Run(domain).execute()
    for c in cases:
        ok, why = True, []
        if c.get("warm"):
            warm = Run(domain).execute()
            verdicts = lambda run: {r["signal"]["id"]: {v["hypothesis_id"]: v["verdict"] for v in r["verdicts"]} for r in run.results}
            cold_v, warm_v = verdicts(base), verdicts(warm)
            changed = sorted(k for k in cold_v if warm_v.get(k) != cold_v[k])
            ok = warm.skipped_by_memory >= 1 and warm.tests_run < base.tests_run and not changed
            why.append(f"cold tests={base.tests_run} warm tests={warm.tests_run} skipped={warm.skipped_by_memory}")
            if changed:
                why.append(f"memory changed the verdict of {len(changed)} signal(s): {', '.join(changed[:8])}")
        else:
            r = _find(base, c.get("signal_contains", ""))
            if r is None:
                ok, why = False, [f"no signal containing '{c.get('signal_contains')}'"]
            else:
                verdict = {v["hypothesis_id"]: v["verdict"] for v in r["verdicts"]}
                for h in c.get("expect_supported", []):
                    if verdict.get(h) != "support":
                        ok = False; why.append(f"{h} expected support, got {verdict.get(h, 'missing')}")
                for h in c.get("expect_rejected", []):
                    if verdict.get(h) != "reject":
                        ok = False; why.append(f"{h} expected reject, got {verdict.get(h, 'missing')}")
                fa = c.get("first_action_contains")
                if fa and (not r["actions"] or fa.lower() not in r["actions"][0]["label"].lower()):
                    ok = False; why.append(f"first action '{r['actions'][0]['label'] if r['actions'] else None}' lacks '{fa}'")
        passed += ok
        report.append({"id": c["id"], "pass": ok, "notes": why})
    out = {"domain": domain.name, "passed": passed, "total": len(cases), "provenance_pct": base.ledger.provenance_pct(),
           "failures": base.failures, "cases": report}
    print(json.dumps(out, indent=1))
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
