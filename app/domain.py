"""Template domain (kept on main so the core is always testable). Replace app/ on an idea branch.
Question: which pump stations fail most, why, and which to service first?"""
from __future__ import annotations
from whycore.domain import Action, Domain, Hypothesis, Signal, TestResult


class PumpDomain(Domain):
    name = "template-pumps"
    title = "Template · pump station outages"
    track = "03"
    question = "Which pump stations fail most, why, and which do we service first?"
    description = "Illustrative seed data. Two competing causes per station: mechanical wear vs grid faults."
    views = {"stations": "SELECT * FROM stations ORDER BY outage_hours_30d DESC"}
    sources = [{"name": "stations.csv (illustrative)", "url": "", "access": "seed", "status": "illustrative"}]

    def scout(self, data, limit):
        sql = "SELECT * FROM stations WHERE outage_hours_30d > 0 ORDER BY outage_hours_30d DESC"
        res = data.run_sql(sql)
        return [Signal(id=r["station_id"], label=f"{r['name']}: {r['outage_hours_30d']} h outage in 30 days",
                       score=float(r["outage_hours_30d"]), props=dict(r), sql=sql, rows=res["rows_n"]) for r in res["rows"][:limit]]

    def hypotheses(self, signal, data):
        return [Hypothesis("wear", "Mechanical wear (old pump, overdue service)"), Hypothesis("grid", "Grid faults upstream")]

    def test(self, signal, hyp, data):
        sid = signal.id
        if hyp.id == "wear":
            sql = f"SELECT pump_age_years, last_service_days FROM stations WHERE station_id = '{sid}'"
            r = data.run_sql(sql); row = r["rows"][0]
            ok = row["pump_age_years"] >= 10 or row["last_service_days"] > 365
            return TestResult("wear", "support" if ok else "reject",
                              f"pump age {row['pump_age_years']} y, last service {row['last_service_days']} d ago ({'overdue' if ok else 'within limits'})", sql, r["rows_n"], dict(row))
        sql = f"SELECT grid_faults_30d FROM stations WHERE station_id = '{sid}'"
        r = data.run_sql(sql); n = r["rows"][0]["grid_faults_30d"]
        return TestResult("grid", "support" if n >= 3 else "reject", f"{n} grid faults in 30 days ({'enough to explain' if n >= 3 else 'too few to explain'} the outage)", sql, r["rows_n"], {"faults": n})

    def plan(self, signal, verdicts, data):
        sup = {v.hypothesis_id for v in verdicts if v.verdict == "support"}
        acts = []
        if "wear" in sup:
            acts.append(Action(f"{signal.id}-svc", f"Service pump at {signal.props['name']}", 1, "wear supported by age/service data"))
        if "grid" in sup:
            acts.append(Action(f"{signal.id}-grid", f"Ask grid operator about faults feeding {signal.props['name']}", 1 if 'wear' not in sup else 2, "grid faults supported"))
        if not acts:
            acts.append(Action(f"{signal.id}-inspect", f"Send an inspector to {signal.props['name']}", 1, "no cause supported; inspect"))
        return acts


DOMAIN = PumpDomain()
