"""Mosca — the crypto-agility agent. Finds every quantum-vulnerable key in YOUR estate, decides which are already late
(Mosca's inequality), drafts the migration order, and — with the Notary hook — signs its own findings with ML-DSA.

Mosca's inequality: an asset is LATE when   shelf_life (x) + migration_time (y)  >  z_year − this_year.
  x comes from data_classes, y from migration_paths, z from algorithms.yaml scenarios. Nothing here is forecast by the
  model; the model only explains verdicts computed from these tables and from real handshakes/scans.

Verdict vocabulary: support = LATE under the primary anchor · uncertain = AT RISK (late only under the earlier anchor)
· reject = SAFE under every anchor (or the hypothesis simply does not apply)."""
from __future__ import annotations
import os
from datetime import date
import yaml
from whycore.domain import Action, Domain, Hypothesis, Signal, TestResult
from whycore.settings import settings

if "MAX_SIGNALS" not in os.environ:      # an inventory wants every asset evaluated, not the top five
    settings.max_signals = 1000
if not os.environ.get("RUN_HOOKS"):      # World Model + Markovian brief, then Notary (signs the brief too) and CBOM
    settings.run_hooks = "whycore.engines:world_model,whycore.engines:brief,app.notary:sign_run,app.cbom:attach"

HERE = os.path.dirname(__file__)
ALG = yaml.safe_load(open(os.path.join(HERE, "algorithms.yaml")))
AS_OF = date.fromisoformat(os.environ["AS_OF"]) if os.environ.get("AS_OF") else date.today()   # evals pin AS_OF
YEAR = AS_OF.year
Z = {s["id"]: s["z_year"] for s in ALG["scenarios"]}
PRIMARY = ALG["primary_scenario"]
EARLIEST = min(Z, key=lambda k: Z[k])
PQ_KEX = [m.lower() for m in ALG["pq_kex_markers"]]
PQ_SIG = [m.lower() for m in ALG["pq_sig_markers"]]
PQ_KEX_SQL = " OR ".join(f"LOWER(COALESCE(a.negotiated_kex, '')) LIKE '%{m}%'" for m in PQ_KEX)
NOT_VULNERABLE = {k.lower() for k, v in ALG["classical"].items() if not v.get("quantum_vulnerable", True)}


def _is_pq(s: str | None, markers: list[str]) -> bool:
    return bool(s) and any(m in str(s).lower() for m in markers)


class MoscaDomain(Domain):
    name = "mosca"
    title = "Mosca · post-quantum crypto-agility agent"
    track = "02"
    question = "Which keys in our estate are already too late to migrate, why, and in what order do we fix them?"
    description = ("Inventory → exposure → Mosca's inequality → migration order → human approval → ML-DSA-signed attestation. "
                   "Seed inventory is ILLUSTRATIVE; run app/data/scanners on your own hosts for a real one. Scans only assets you own.")
    views = {
        "inventory": "SELECT asset_id, name, kind, algorithm, key_bits, purpose, negotiated_kex, data_class, in_use, source FROM assets ORDER BY asset_id",
        "clock": f"""SELECT a.asset_id, a.name, a.kind, a.algorithm, d.shelf_life_years AS x, m.migration_years AS y,
                    ({Z[PRIMARY]} - d.shelf_life_years - m.migration_years) AS start_by_year,
                    CASE WHEN a.purpose = 'confidentiality' AND ({PQ_KEX_SQL}) THEN 'HYBRID KEX'
                         WHEN ({Z[PRIMARY]} - d.shelf_life_years - m.migration_years) < {YEAR} THEN 'LATE'
                         WHEN ({Z[EARLIEST]} - d.shelf_life_years - m.migration_years) < {YEAR} THEN 'AT RISK' ELSE 'SAFE' END AS status
                    FROM assets a JOIN data_classes d ON a.data_class = d.data_class JOIN migration_paths m ON a.kind = m.kind
                    WHERE a.in_use = true ORDER BY start_by_year""",
        "data_classes": "SELECT * FROM data_classes ORDER BY shelf_life_years",
        "migration_paths": "SELECT * FROM migration_paths",
        "scenarios": "SELECT * FROM scenarios ORDER BY z_year",
    }
    sources = [
        {"name": "NIST FIPS 203 / 204 / 205 (ML-KEM, ML-DSA, SLH-DSA)", "url": "https://csrc.nist.gov/projects/post-quantum-cryptography", "access": "public", "status": "reference"},
        {"name": "NIST IR 8547 transition timeline (2030 deprecate, 2035 disallow)", "url": "https://csrc.nist.gov/pubs/ir/8547/ipd", "access": "public", "status": "reference"},
        {"name": "Certificate Transparency logs for your own domains (crt.sh)", "url": "https://crt.sh", "access": "public, read-only", "status": "scanner app/data/scanners/scan_ct.py"},
        {"name": "TLS / SSH handshakes of your own hosts", "url": "", "access": "own targets.yaml only", "status": "scanners scan_tls.py / scan_ssh.py"},
        {"name": "Repos, firmware images, configs you own", "url": "", "access": "local paths", "status": "scan_repo.py / scan_firmware.py"},
        {"name": "Seed inventory in app/data/seed", "url": "", "access": "seed", "status": "illustrative"},
    ]

    # ---- scout --------------------------------------------------------------------------------------------------
    def scout(self, data, limit):
        sql = f"""SELECT a.*, d.shelf_life_years AS x, m.migration_years AS y,
                        (d.shelf_life_years + m.migration_years) - ({Z[PRIMARY]} - {YEAR}) AS overshoot_primary,
                        (d.shelf_life_years + m.migration_years) - ({Z[EARLIEST]} - {YEAR}) AS overshoot_earliest
                 FROM assets a JOIN data_classes d ON a.data_class = d.data_class JOIN migration_paths m ON a.kind = m.kind
                 ORDER BY overshoot_primary DESC, a.traffic_gb_month DESC"""
        res = data.run_sql(sql)
        out = []
        for r in res["rows"]:
            pq = _is_pq(r["negotiated_kex"], PQ_KEX) or _is_pq(r["negotiated_sig"], PQ_SIG) or _is_pq(r["algorithm"], PQ_KEX + PQ_SIG)
            dead = (not r["in_use"]) or (r["expires"] and str(r["expires"]) < AS_OF.isoformat())
            urgency = max(float(r["overshoot_primary"]), 0) * 3 + max(float(r["overshoot_earliest"]), 0) + (0.1 * (float(r["traffic_gb_month"] or 0) ** 0.5))
            if pq:
                urgency = 0.05          # still listed once, so the UI shows it as recognised-safe
            if dead:
                urgency = 0.2
            if r["purpose"] == "signature" and not pq:
                urgency = max(urgency, 1.0)
            label = f"{r['name']}: {r['algorithm']}" + (f" {r['key_bits']}" if r["key_bits"] else "") + \
                    (f", kex {r['negotiated_kex']}" if r["negotiated_kex"] else "") + f" · protects {r['data_class']} ({r['x']} y)"
            # memory generalises across assets only when every input the tests read is the same: kind, algorithm, data class
            # (x and y), purpose, PQ markers, dead/alive, and whether the signature expires before the earliest anchor.
            exp_early = bool(r["expires"]) and int(str(r["expires"])[:4]) <= Z[EARLIEST]
            pq_s = _is_pq(r["negotiated_sig"], PQ_SIG) or _is_pq(r["algorithm"], PQ_SIG)
            props = dict(r); props.update({"memory_key": f"{r['kind']}|{r['algorithm']}|{r['data_class']}|{r['purpose']}|kex_pq={pq}|sig_pq={pq_s}|dead={bool(dead)}|exp_early={exp_early}"})
            out.append(Signal(id=r["asset_id"], label=label, score=round(urgency, 3), props=props, sql=sql, rows=res["rows_n"]))
        out.sort(key=lambda s: -s.score)
        return out[:limit]

    # ---- hypotheses ----------------------------------------------------------------------------------------------
    def hypotheses(self, signal, data):
        return [Hypothesis("harvest_now_decrypt_later", "Traffic/data protected by this key can be recorded now and read once a CRQC exists"),
                Hypothesis("forgery_after_qday", "Signatures made with this key could be forged once a CRQC exists, while they still matter"),
                Hypothesis("already_hybrid", "The asset already negotiates a post-quantum (hybrid) mechanism"),
                Hypothesis("dead_asset", "The asset is expired or no longer in use; retire it instead of migrating it")]

    # ---- tests ----------------------------------------------------------------------------------------------------
    def test(self, signal, hyp, data):
        # One Zetaris statement per run: every test reads its asset's row from the scout query (assets × data_classes ×
        # migration_paths, x and y included) and cites that statement; data.asset_id names the row.
        r, sql, n = signal.props, signal.sql, signal.rows
        res = self._test(r, hyp, sql, n)
        res.sql_executed = signal.sql_executed
        res.data = {"asset_id": r["asset_id"], **(res.data or {})}
        return res

    def _test(self, r, hyp, sql, n):
        x, y = float(r["x"]), float(r["y"])
        rem_p, rem_e = Z[PRIMARY] - YEAR, Z[EARLIEST] - YEAR
        pq_kex = _is_pq(r["negotiated_kex"], PQ_KEX) or _is_pq(r["algorithm"], PQ_KEX)
        pq_sig = _is_pq(r["negotiated_sig"], PQ_SIG) or _is_pq(r["algorithm"], PQ_SIG)
        dead = (not r["in_use"]) or (bool(r["expires"]) and str(r["expires"]) < AS_OF.isoformat())
        symmetric = str(r["algorithm"] or "").lower() in NOT_VULNERABLE
        if symmetric and hyp.id in ("harvest_now_decrypt_later", "forgery_after_qday"):
            return TestResult(hyp.id, "reject", f"{r['algorithm']} is symmetric (algorithms.yaml: quantum_vulnerable false); Shor does not apply", sql, n)
        if hyp.id == "already_hybrid":
            if pq_kex or pq_sig:
                return TestResult(hyp.id, "support", f"negotiated {r['negotiated_kex'] or r['negotiated_sig'] or r['algorithm']}: post-quantum mechanism present; no migration needed for this hop", sql, n, {"kex": r["negotiated_kex"]})
            return TestResult(hyp.id, "reject", f"negotiated {r['negotiated_kex'] or r['negotiated_sig'] or r['algorithm']}: classical only, no ML-KEM/ML-DSA marker", sql, n)
        if hyp.id == "dead_asset":
            if dead:
                why = "not in use" if not r["in_use"] else f"expired {r['expires']}"
                return TestResult(hyp.id, "support", f"{why}: retire, do not migrate", sql, n)
            return TestResult(hyp.id, "reject", f"in use{', valid until ' + str(r['expires']) if r['expires'] else ''}", sql, n)
        if hyp.id == "harvest_now_decrypt_later":
            if r["purpose"] not in ("confidentiality", "both"):
                return TestResult(hyp.id, "reject", "signature-only asset: nothing confidential is protected by it", sql, n)
            if pq_kex:
                return TestResult(hyp.id, "reject", f"key exchange already hybrid ({r['negotiated_kex']})", sql, n)
            if dead:
                return TestResult(hyp.id, "reject", "asset is dead; retirement covers it", sql, n)
            ineq = f"x+y = {x:g}+{y:g} = {x + y:g} y"
            if x + y > rem_p:
                return TestResult(hyp.id, "support", f"LATE: {ineq} > {rem_p} y left to {Z[PRIMARY]} ({PRIMARY}); start-by year {Z[PRIMARY] - x - y:g} has passed", sql, n, {"x": x, "y": y, "z": Z[PRIMARY]})
            if x + y > rem_e:
                return TestResult(hyp.id, "uncertain", f"AT RISK: {ineq} ≤ {rem_p} y to {Z[PRIMARY]} but > {rem_e} y to {Z[EARLIEST]} ({EARLIEST}); start by {Z[PRIMARY] - x - y:g}", sql, n, {"x": x, "y": y})
            return TestResult(hyp.id, "reject", f"SAFE under every anchor: {ineq} ≤ {rem_e} y to {Z[EARLIEST]}", sql, n, {"x": x, "y": y})
        if hyp.id == "forgery_after_qday":
            # Signatures are not retroactively broken: the risk is a forgery AFTER a CRQC exists while the signature
            # still matters. LATE when the signature must stay trustworthy beyond the primary anchor; AT RISK when it
            # must outlive the earliest anchor or migration itself takes longer than the time to that anchor.
            if r["purpose"] not in ("signature", "both"):
                return TestResult(hyp.id, "reject", "confidentiality-only asset: it signs nothing", sql, n)
            if pq_sig:
                return TestResult(hyp.id, "reject", f"signatures already post-quantum ({r['negotiated_sig'] or r['algorithm']})", sql, n)
            if dead:
                return TestResult(hyp.id, "reject", "asset is dead; retirement covers it", sql, n)
            exp_year = int(str(r["expires"])[:4]) if r["expires"] else None
            if exp_year and exp_year <= Z[EARLIEST] and x <= rem_e:
                return TestResult(hyp.id, "reject", f"signature validity ends {exp_year}, before the earliest anchor {Z[EARLIEST]}; rotate at renewal", sql, n)
            horizon = f"must stay trustworthy {x:g} y{' (+' + format(y, 'g') + ' y to migrate)' if y else ''}"
            if x > rem_p:
                return TestResult(hyp.id, "support", f"LATE: signatures {horizon}, beyond {rem_p} y to {Z[PRIMARY]} ({PRIMARY}); a CRQC could forge them while they still count", sql, n, {"x": x, "y": y, "z": Z[PRIMARY]})
            if x > rem_e or y > rem_e:
                return TestResult(hyp.id, "uncertain", f"AT RISK: {horizon}; exceeds {rem_e} y to {Z[EARLIEST]} ({EARLIEST}); rotate before then", sql, n, {"x": x, "y": y})
            return TestResult(hyp.id, "reject", f"SAFE: {horizon}, within {rem_e} y to {Z[EARLIEST]}; rotate at next renewal", sql, n, {"x": x, "y": y})
        return TestResult(hyp.id, "uncertain", "unknown hypothesis")

    # ---- plan -----------------------------------------------------------------------------------------------------
    def plan(self, signal, verdicts, data):
        p = signal.props
        v = {t.hypothesis_id: t.verdict for t in verdicts}
        tgt = ALG["targets"].get(p["kind"], {"target": "post-quantum replacement", "how": "see vendor guidance"})
        acts: list[Action] = []
        if v.get("dead_asset") == "support":
            acts.append(Action(f"{signal.id}-retire", f"Retire {p['name']} (revoke/remove key, close port)", 1, "expired or unused; migrating a dead asset is wasted work",
                               {"apply": f"# revoke and remove {p['host']}:{p['port']}", "rollback": "n/a", "blast_radius": "none"}))
            return acts
        if v.get("already_hybrid") == "support":
            acts.append(Action(f"{signal.id}-record", f"Record {p['name']} as post-quantum ready in the CBOM", 3, f"negotiates {p['negotiated_kex'] or p['negotiated_sig']}", {"apply": "cbom: mark pq_ready=true", "blast_radius": "none"}))
            if v.get("forgery_after_qday") not in ("support", "uncertain"):
                return acts      # hybrid key exchange and no signature at risk: nothing else to do
        if v.get("harvest_now_decrypt_later") in ("support", "uncertain"):
            pr = 1 if v["harvest_now_decrypt_later"] == "support" else 2
            acts.append(Action(f"{signal.id}-kex", f"Move {p['name']} to {tgt['target']}", pr,
                               f"{'LATE' if pr == 1 else 'AT RISK'} by Mosca's inequality; {tgt['how']}",
                               {"apply": self._apply_cmd(p), "rollback": "restore previous config (kept in the ledger)", "blast_radius": f"{p['traffic_gb_month']} GB/month re-handshakes; client support check required", "verify": "re-run scan_tls/scan_ssh and confirm the negotiated group"}))
        if v.get("forgery_after_qday") in ("support", "uncertain"):
            pr = 1 if v["forgery_after_qday"] == "support" else 2
            sig_kind = p["kind"] if p["kind"] in ("firmware_sig", "doc_sig", "repo_key") else "ssh_hostkey" if p["kind"] == "ssh" else "cert"
            sig_t = ALG["targets"][sig_kind]
            acts.append(Action(f"{signal.id}-sig", f"Re-key signatures for {p['name']} → {sig_t['target']}", pr, sig_t["how"],
                               {"apply": "dual-sign (classical + ML-DSA) during transition; flip verifier to require ML-DSA", "rollback": "verifier accepts classical until fleet confirms", "blast_radius": "all verifiers of this key"}))
        if p["kind"] == "repo_key":
            acts.append(Action(f"{signal.id}-hygiene", f"Remove private key from {p['host']} and rotate it", 1, "a long-lived private key in a repository is a risk regardless of quantum timelines",
                               {"apply": "git filter-repo to purge; rotate on the consumer side; store in secrets manager", "blast_radius": "every system trusting the old key"}))
        if not acts:
            acts.append(Action(f"{signal.id}-watch", f"Watch {p['name']}; re-evaluate at renewal", 3, "safe under every anchor today", {"apply": "none"}))
        return acts

    def on_approve(self, signal, action):
        """Called by whycore only when a human clicks Approve. Mosca never changes a real system: for every real asset the
        approved draft is the operator's to apply. The single exception is the demo fixture (a throwaway container listed
        under `demo:` in targets.yaml, docs/demo.md): its key-exchange draft is applied by switching the fixture to the
        hybrid group, through the fixture's own token-protected control endpoint (DEMO_APPLY_URL, DEMO_APPLY_TOKEN)."""
        p = signal["props"]
        if "DEMO FIXTURE" not in str(p.get("note") or ""):
            return {"applied": False, "message": "approved; real asset, so the operator applies it (Mosca changes nothing on real systems)"}
        if not action["id"].endswith("-kex"):
            return {"applied": False, "message": "approved; only the key-exchange draft is applied on the demo fixture"}
        url, tok = os.environ.get("DEMO_APPLY_URL", ""), os.environ.get("DEMO_APPLY_TOKEN", "")
        from urllib.parse import urlparse
        if not (url and tok) or urlparse(url).hostname != p["host"]:
            return {"applied": False, "message": "approved; DEMO_APPLY_URL does not point at this fixture, apply with demo_fixture.sh apply"}
        import httpx
        r = httpx.post(url.rstrip("/") + "/apply", json={"groups": "X25519MLKEM768:X25519"}, headers={"Authorization": f"Bearer {tok}"}, timeout=15)
        r.raise_for_status()
        st = r.json()
        return {"applied": True, "message": f"{p['host']}:{p['port']} now offers {st['groups']} (since {st['changed_at']}); "
                                            "re-scan to confirm the negotiated group: demo_fixture.sh rescan"}

    @staticmethod
    def _apply_cmd(p: dict) -> str:
        k = p["kind"]
        if k == "tls":
            return f"# origin/proxy for {p['host']}:{p['port']} — enable hybrid group\nssl_ecdh_curve X25519MLKEM768:X25519;   # nginx 1.27+ / OpenSSL 3.5+\n# then: openssl s_client -connect {p['host']}:{p['port']} -groups X25519MLKEM768 | grep 'Negotiated TLS1.3 group'"
        if k == "ssh":
            return f"# /etc/ssh/sshd_config on {p['host']}\nKexAlgorithms mlkem768x25519-sha256,sntrup761x25519-sha512,curve25519-sha256\n# sshd -t && systemctl reload ssh"
        if k == "vpn":
            return "# WireGuard interim: PresharedKey = <32-byte PSK> per peer; plan vendor hybrid KEM"
        return "# see Planner rationale"

    @staticmethod
    def status_of(verdicts) -> str:
        v = {t.hypothesis_id: t.verdict for t in verdicts}
        risks = (v.get("harvest_now_decrypt_later"), v.get("forgery_after_qday"))
        if v.get("dead_asset") == "support":
            return "DEAD (retire)"
        if "support" in risks:
            return "LATE"
        if "uncertain" in risks:
            return "AT RISK"
        return "SAFE"

    brief_goal = ("Which keys in our estate are already too late to migrate, why, and in what order do we fix them? Write a brief "
                  "for an engineering manager: group the assets by verdict (a risk hypothesis with support = LATE, uncertain = "
                  "AT RISK, every risk rejected = SAFE, dead_asset support = retire), name the asset ids, and give the order of "
                  "work. Use only the facts in the attachment; never invent dates, numbers or assets.")

    def explain_prompt(self, signal, verdicts, actions):
        sys_ = ("You explain post-quantum migration verdicts to an engineering manager in at most 110 words. Use only the numbers given. "
                "Mosca's inequality: shelf life + migration time > years until a cryptographically relevant quantum computer ⇒ already late. "
                "Never state when a quantum computer will exist; the anchors are policy dates.")
        lines = [f"Asset: {signal.label}", f"Overall status: {self.status_of(verdicts)} (use exactly this word; say late only if it is LATE)"] + \
                [f"- {v.hypothesis_id}: {v.verdict.upper()} — {v.reason}" for v in verdicts] + \
                ["Draft actions: " + "; ".join(f"{a.priority}. {a.label}" for a in actions)]
        return sys_, "\n".join(lines)

    def extra_json(self, data):
        rows = data.run_sql(self.views["clock"])["rows"]
        return {"center": [50.73, 7.1], "zoom": 5,
                "cards": [{"title": f"The clock — start-by year under the {PRIMARY} anchor (z = {Z[PRIMARY]})",
                           "note": f"start_by = z − shelf life − migration time. Anything before {YEAR} is already late. HYBRID KEX = a confidentiality-only asset that already negotiates a post-quantum hybrid, so the inequality no longer applies to it (see its verdict). Anchors: " + ", ".join(f"{k}={v}" for k, v in Z.items()),
                           "columns": ["asset_id", "name", "kind", "algorithm", "x", "y", "start_by_year", "status"], "rows": rows}]}


DOMAIN = MoscaDomain()
