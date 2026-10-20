"""Eval runner shared by every idea: python -m whycore.evals [app/evals.yaml] [--keep-memory]

env:                                      # optional: applied before whycore reads its settings (existing env wins)
  SEED_DIR: app/data/inventory            # e.g. evaluate a real inventory instead of the illustrative seed
  AS_OF: "2026-10-20"
cases:
  - id: salt_veendam
    signal_contains: "Veendam"            # a signal whose label contains this must exist
    expect_supported: [salt]              # hypothesis ids that must be supported for that signal
    expect_rejected: [gas]                # hypothesis ids that must be rejected
    expect_uncertain: []                  # hypothesis ids that must stay uncertain
    arithmetic: "..."                     # optional: why these verdicts follow from the data; printed with the result
    first_action_contains: "dike"         # the top action's label must contain this (optional)
  - id: warm_run
    warm: true                            # run twice; second run must skip ≥1 hypothesis via memory AND reach the
                                          # same verdict for every signal (memory may save work, never change answers)
Scores: pass/fail per case, provenance %, tests cold vs warm.
"""
from __future__ import annotations
import importlib, json, os, sys
import yaml


def _find(run, needle: str) -> dict | None:
    for r in run.results:
        if needle.lower() in r["signal"]["label"].lower():
            return r
    return None


def main(argv: list[str]) -> int:
    path = next((a for a in argv if a.endswith((".yaml", ".yml"))), "app/evals.yaml")
    keep = "--keep-memory" in argv
    spec = yaml.safe_load(open(path))
    for k, v in (spec.get("env") or {}).items():       # before any whycore module reads the environment
        os.environ.setdefault(k, str(v))
    seed = os.environ.get("SEED_DIR")
    if seed and not os.path.isdir(seed):
        print(json.dumps({"error": f"SEED_DIR {seed} does not exist (this eval file needs that data)"})); return 2
    from whycore.memory import memory
    from whycore.pipeline import Run
    domain = importlib.import_module(os.environ.get("DOMAIN_MODULE", "app.domain")).DOMAIN
    cases = spec["cases"]
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
                for h in c.get("expect_uncertain", []):
                    if verdict.get(h) != "uncertain":
                        ok = False; why.append(f"{h} expected uncertain, got {verdict.get(h, 'missing')}")
                fa = c.get("first_action_contains")
                if fa and (not r["actions"] or fa.lower() not in r["actions"][0]["label"].lower()):
                    ok = False; why.append(f"first action '{r['actions'][0]['label'] if r['actions'] else None}' lacks '{fa}'")
        passed += ok
        entry = {"id": c["id"], "pass": ok, "notes": why}
        if c.get("arithmetic"):
            entry["arithmetic"] = c["arithmetic"]
        report.append(entry)
    out = {"domain": domain.name, "data": {"backend": os.environ.get("DATA_BACKEND", "duckdb"), "seed_dir": seed, "as_of": os.environ.get("AS_OF")},
           "passed": passed, "total": len(cases), "provenance_pct": base.ledger.provenance_pct(),
           "failures": base.failures, "cases": report}
    print(json.dumps(out, indent=1))
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
