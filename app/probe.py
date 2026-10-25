"""Probe loop: the one step where a model chooses what to look at next (run hook app.probe:loop, before the Notary).

For every LATE or AT RISK asset the Investigator asks Nemotron (the fast model) for one rival cause the four fixed
hypotheses did not cover, plus one read-only SELECT over Mosca's tables that returns rows only if that cause holds. The
Skeptic runs the statement through Zetaris and the row count decides (rows = supported, none = rejected); the model
never sets a verdict. The next round sees what the earlier rounds found, and the loop stops when the model has
nothing new or after PROBE_ROUNDS rounds. A supported probe adds a draft action, which waits for a human like any other.

Fast by construction: assets are probed in parallel, the hook runs while the Explainer waits on the model, and model
answers are cached by prompt, so a repeat run on unchanged evidence replays its rounds without a model call (the
queries still run, so the verdicts are always current). Every probe is a ledger claim carrying its SQL, so the
attestation signs it. Statements that are not a single SELECT over the five tables are refused, never run.
"""
from __future__ import annotations
import json, os, re
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from whycore.data import data
from whycore.ledger import Claim
from whycore.memory import memory
from whycore.model import model

MAX_ROUNDS = int(os.environ.get("PROBE_ROUNDS", "3"))
WORKERS = int(os.environ.get("PROBE_WORKERS", "8"))
TABLES = {"assets", "probes", "data_classes", "migration_paths", "scenarios"}
FORBIDDEN = re.compile(r"(?i)\b(insert|update|delete|drop|alter|create|grant|revoke|truncate|copy|call|exec|execute|merge|"
                       r"attach|detach|pragma|set|into|load|install|refresh|cache|uncache|msck|dblink|information_schema|pg_\w+)\b")
SYSTEM = """You are the Investigator in a post-quantum cryptography audit of the owner's own estate.
An asset was tested against four fixed hypotheses (harvest_now_decrypt_later, forgery_after_qday, already_hybrid,
dead_asset). Propose ONE further cause that could change what the owner should do about this asset and that the
columns below can actually show. Then write one query that returns rows ONLY if that cause holds for this asset.
What the data can show: other assets on the same host (host) with weak algorithms or small keys (algorithm, key_bits);
an expiry date (expires) falling before the migration could finish (migration_paths.migration_years); the asset
having no expiry at all (expires IS NULL) while in use; other assets of the same data_class that share its kind and
algorithm; failed or missing handshakes for its host in probes (target LIKE '%host%', outcome).
What it cannot show: key fingerprints, key reuse between hosts, who has access, patch levels. Do not propose those.
The query must test the cause itself, not something weaker (finding other Ed25519 keys does not show reuse).
Classically weak means: RSA below 2048 bits, DSA, or ECDSA below 256 bits. Ed25519 and ECDSA-256 are classically fine
(every RSA/ECC key is quantum-vulnerable anyway, which the fixed hypotheses already cover). Algorithm names are stored
as RSA, ECDSA, Ed25519, X25519 (match case-insensitively with upper()). When looking for OTHER assets, exclude this one
with asset_id != '<its asset_id>'.
Do not repeat a cause from earlier_probes; if an earlier probe failed with an error, you may fix that query instead.
Reply with JSON only:
{"done": false, "cause": "snake_case_name", "label": "one sentence stating exactly what the rows mean", "sql": "...", "action": "what to do if it holds, imperative, under 90 characters"}
or {"done": true} when nothing new is worth testing.
Tables (Spark SQL, read-only):
 assets(asset_id, name, host, port, kind, algorithm, key_bits, purpose, negotiated_kex, negotiated_sig, expires, in_use, data_class, traffic_gb_month, source, found_at, note)
 probes(source, target, outcome, probed_at)
 data_classes(data_class, shelf_life_years, examples)
 migration_paths(kind, migration_years, vendor_ready, note)
 scenarios(scenario, z_year, note)
Spark SQL notes: expires is a 'YYYY-MM-DD' string, compare with to_date(expires); add days with
date_add(current_date(), n); key_bits is a string, compare with CAST(key_bits AS INT); in_use = true.
Use only these tables and columns. Compare text with single quotes. No comments, no semicolons, at most 50 rows."""


def safe_sql(sql: str) -> str | None:
    """A single SELECT over Mosca's own tables, or None. Anything else is refused before it reaches Zetaris."""
    s = str(sql or "").strip().rstrip(";").strip()
    if not s or ";" in s or "--" in s or "/*" in s or not re.match(r"(?is)^select\s", s) or FORBIDDEN.search(s):
        return None
    names = {n.lower() for n in re.findall(r"(?i)\b(?:from|join)\s+([a-z_][\w.]*)", s)}
    if not names or not names <= TABLES:
        return None
    return s if re.search(r"(?i)\blimit\s+\d+\s*$", s) else s + " LIMIT 50"


def _probe(run, r: dict) -> None:
    sid, p = r["signal"]["id"], r["signal"]["props"]
    facts = {k: p.get(k) for k in ("asset_id", "name", "host", "kind", "algorithm", "key_bits", "purpose", "negotiated_kex",
                                    "negotiated_sig", "expires", "in_use", "data_class", "source", "x", "y")}
    tested = {v["hypothesis_id"]: v["verdict"] for v in r["verdicts"]}
    probes: list[dict] = []
    for rnd in range(1, MAX_ROUNDS + 1):
        user = json.dumps({"asset": facts, "fixed_hypotheses": tested,
                           # a failed query goes back with its error, so the next round can repair it
                           "earlier_probes": [{k: q.get(k) for k in ("cause", "verdict", "rows", "sql", "error") if q.get(k) is not None}
                                              for q in probes]}, default=str, sort_keys=True)
        run.ledger.step("investigator", "asks the model", signal=sid, round=rnd, probe=True)
        try:
            text, meta = model.answer(SYSTEM, user, deep=False, json_mode=True, max_tokens=320)
            ask = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
        except Exception as e:
            run.ledger.step("investigator", "no usable answer", signal=sid, round=rnd, probe=True, error=str(e)[:120])
            break
        if ask.get("done") or not ask.get("sql"):
            run.ledger.step("investigator", "nothing new to test", signal=sid, round=rnd, probe=True)
            break
        cause = re.sub(r"[^a-z0-9_]+", "_", str(ask.get("cause") or "probe").lower()).strip("_")[:48] or "probe"
        label = str(ask.get("label") or cause)[:200]
        q = {"round": rnd, "cause": cause, "label": label, "model": meta.get("model"), "cached": bool(meta.get("cached"))}
        sql = safe_sql(ask["sql"])
        if not sql:
            q.update(verdict="refused", rows=0, sql=str(ask["sql"])[:400])
            run.ledger.step("skeptic", "refused", signal=sid, hypothesis=cause, label=label, probe=True, reason="not a single read-only SELECT on Mosca's tables")
            probes.append(q)
            continue
        try:
            res = data.run_sql(sql)
        except Exception as e:
            # keep the part of Zetaris' answer that says what is wrong ("[UNRESOLVED_COLUMN...] ... `key_id` ...")
            m = re.search(r"\[[A-Z_.]+\][^\\\"]{0,160}|ParseException[^\\\"]{0,120}", str(e))
            msg = re.sub(r"\s+", " ", m.group(0) if m else str(e)[:200])[:200]
            q.update(verdict="error", rows=0, sql=sql, error=msg)
            run.ledger.step("skeptic", "query failed", signal=sid, hypothesis=cause, label=label, probe=True, reason=msg[:120])
            probes.append(q)
            continue
        n = res["rows_n"]
        if re.search(r"(?i)\bother", label) and res["rows"] and isinstance(res["rows"][0], dict) and "asset_id" in res["rows"][0]:
            n = sum(1 for row in res["rows"] if row.get("asset_id") != sid)     # "other assets" never counts the asset itself
        verdict = "support" if n else "reject"
        q.update(verdict=verdict, rows=n, sql=sql, sql_executed=res["sql_executed"], sample=res["rows"][:3])
        probes.append(q)
        run.ledger.add(Claim(text=f"probe {cause} on {sid}: {label}", kind="probe", sql=sql, sql_executed=res["sql_executed"],
                             source=data.mode, rows=n, status="supported" if n else "rejected",
                             data={"round": rnd, "signal": sid, "model": meta.get("model"), "cached": bool(meta.get("cached"))}))
        run.ledger.step("skeptic", verdict, signal=sid, hypothesis=cause, label=label, rows=n, probe=True,
                        reason=f"{n} row{'s' if n != 1 else ''} from Zetaris")
        if n and ask.get("action"):
            a = {"id": f"{sid}-probe-{cause}", "label": str(ask["action"])[:140], "priority": len(r["actions"]) + 1,
                 "rationale": f"found by probe round {rnd}: {label} ({n} rows)", "props": {"probe": cause}, "status": "draft"}
            d = memory.decision(a["id"], a["label"])          # a decision on the same follow-up carries over, as for any draft
            if d:
                a.update(status=d["status"], decided_in=d["run_id"], decided_at=d["t"])
            r["actions"].append(a)
            run.ledger.step("planner", "follow-up drafted", signal=sid, first=a["label"], probe=True)
    r["probes"] = probes


def loop(run) -> None:
    targets = [r for r in run.results if run.domain.status_of([SimpleNamespace(**v) for v in r["verdicts"]]) in ("LATE", "AT RISK")]
    with ThreadPoolExecutor(max_workers=max(1, WORKERS)) as ex:
        list(ex.map(lambda r: _probe(run, r), targets))
    n = sum(len(r.get("probes", [])) for r in targets)
    run.extras["probes"] = {"assets": len(targets), "probes": n, "rounds_max": MAX_ROUNDS,
                            "supported": sum(1 for r in targets for q in r.get("probes", []) if q["verdict"] == "support")}


loop.explanation_free = True     # reads verdicts and actions only, so it runs while the Explainer waits on the model
