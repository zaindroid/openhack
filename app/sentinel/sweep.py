"""Sentinel sweep: snapshot the owner's hosts, compare with their baseline, publish findings for Zetaris.

  python app/sentinel/sweep.py            hosts in targets.yaml `sentinel:` marked local (cron: every minute)
  python app/sentinel/sweep.py --remote   hosts reached over SSH, one batched call per host (cron: every 5 minutes)
  python app/sentinel/sweep.py --cves     also check installed packages against OSV (otherwise at most every 6 hours)

Only hosts listed under `sentinel:` in targets.yaml are touched, with probe_host.py (read-only; see its docstring).
The first sweep of a host sets its baseline and reports nothing. Later sweeps report what differs:

  new listener / listener gone · SSH brute force (>= 10 failures from one source in the window) · SSH login from a
  source never seen before · password login · watched file changed / added / removed · new enabled systemd unit ·
  process running from /tmp, /dev/shm or /var/tmp · new container · container gained privileged / host network /
  host pid / docker.sock / / mount / public port · package with a medium, high or critical CVE that has a fix

A finding stays open until the owner decides in the vault: "expected" folds the new value into the baseline,
"incident" keeps it on record. Nothing on a host is changed, blocked or killed by the sentinel.

Evidence: each snapshot's sha256 is on its sweep row and on every finding it raised; snapshots are kept under
app/data/sentinel/<host>/ for 7 days. Published as Parquet to s3://mosca/sentinel/current/{findings,sweeps}/ (Zetaris
mosca_s3.sentinel_findings / mosca_s3.sentinel_sweeps), then the app is pinged to read them."""
from __future__ import annotations
import hashlib, io, json, os, re, ssl, subprocess, sys, time, urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
STATE = os.environ.get("SENTINEL_DIR", os.path.join(ROOT, "app", "data", "sentinel"))
PROBE = os.path.join(HERE, "probe_host.py")
APP = os.environ.get("SENTINEL_APP", "https://127.0.0.1")
APP_HOST = os.environ.get("SENTINEL_APP_HOST", "mosca.zaindroid.me")
CVE_EVERY_S = 6 * 3600
BRUTE = 10
SEV = {"critical": 4, "high": 3, "medium": 2, "low": 1}
CRIT_FILES = ("authorized_keys", "sudoers", "/etc/shadow", "/etc/passwd", "ld.so.preload", "sshd_config")
sys.path.insert(0, os.path.join(ROOT, "app", "data", "scanners"))


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fid(*parts) -> str:
    return hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:12]


def load(path: str, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save(path: str, obj) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w") as f:
        json.dump(obj, f, sort_keys=True)
    os.replace(path + ".tmp", path)


# ---- snapshot ----------------------------------------------------------------------------------------------------
def snapshot(h: dict) -> dict:
    src = open(PROBE, "rb").read()
    if h.get("local"):
        cmd = ["sudo", "-n", "python3", "-"]
    else:   # one SSH call per host per sweep (fail2ban on the VPS counts connections)
        cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", h["ssh"],
               'if [ "$(id -u)" = 0 ]; then exec python3 -; else exec sudo -n python3 -; fi']
    out = subprocess.run(cmd, input=src, capture_output=True, timeout=120).stdout
    return json.loads(out)


# ---- compare -----------------------------------------------------------------------------------------------------
def cname(n: str) -> str:
    return re.sub(r"-\d{9,}$", "", n)          # Coolify adds a deploy suffix; the service is the same


def diff(host: str, base: dict, snap: dict, seen_src: set) -> list[dict]:
    out = []

    def f(check, sev, title, subject, value="", detail="", base_value=""):
        out.append({"finding_id": fid(host, check, subject, value), "host": host, "check": check, "severity": sev, "title": title,
                    "subject": str(subject), "value": str(value), "baseline_value": str(base_value), "detail": detail})

    key = lambda p: f"{p['proto']} {p['addr']}:{p['port']}"
    bp, sp = {key(p): p for p in base["ports"]}, {key(p): p for p in snap["ports"]}
    for k in sp.keys() - bp.keys():
        public = sp[k]["addr"] in ("0.0.0.0", "*", "::")
        f("port_new", "high" if public else "medium", f"new {'public ' if public else ''}listener {k} ({sp[k]['proc'] or 'unknown process'})", k, sp[k]["proc"])
    for k in bp.keys() - sp.keys():
        f("port_gone", "low", f"listener {k} ({bp[k]['proc']}) closed", k, "gone", base_value=bp[k]["proc"])

    for src, n in snap["auth"]["failed"].items():
        if n >= BRUTE:
            f("ssh_bruteforce", "high", f"SSH brute force: {n} failed logins from {src} in {snap['auth']['since_min']} min", src,
              snap["time"][:13], detail=f"{n} failures")
    for a in snap["auth"]["accepted"]:
        if a["src"] not in seen_src:
            f("ssh_new_source", "high", f"SSH login as {a['user']} from a new source {a['src']} ({a['method']})", a["src"], a["user"],
              detail=f"{a['t']} {a['method']} {a['key']}".strip())
        if a["method"] == "password":
            f("ssh_password", "medium", f"password login as {a['user']} from {a['src']}", f"{a['user']}@{a['src']}", "password", detail=a["t"])

    bf, sf = base["files"], snap["files"]
    sev = lambda p: "high" if any(c in p for c in CRIT_FILES) else "medium"
    for p in sf.keys() | bf.keys():
        if p not in bf:
            f("file_added", "critical" if "ld.so.preload" in p else sev(p), f"new file {p}", p, sf[p][:16])
        elif p not in sf:
            f("file_removed", "low", f"file removed {p}", p, "gone", base_value=bf[p][:16])
        elif sf[p] != bf[p]:
            f("file_changed", sev(p), f"{p} changed", p, sf[p][:16], base_value=bf[p][:16])

    for u in set(snap["units"]) - set(base["units"]):
        f("unit_new", "medium", f"new enabled systemd unit {u}", u, "enabled")

    for p in snap["procs"]:
        if not p["exe"].endswith(" (deleted)") or p["exe"].startswith(("/tmp/", "/dev/shm/", "/var/tmp/")):
            f("proc_tmp", "critical", f"process {p['comm']} (pid {p['pid']}) runs from {p['exe']}", p["exe"], p["comm"])

    bc = {cname(c["name"]): c for c in base["containers"]}
    for c in snap["containers"]:
        n, b = cname(c["name"]), bc.get(cname(c["name"]))
        if not b:
            f("container_new", "low", f"new container {n} ({c['image'][:60]})", n, c["image"][:60])
            b = {}
        for flag, what in (("privileged", "privileged"), ("net_host", "host network"), ("pid_host", "host pid namespace"),
                           ("docker_sock", "docker.sock mounted"), ("root_mount", "host / mounted")):
            if c[flag] and not b.get(flag):
                f("container_risk", "high", f"container {n}: {what}", f"{n}:{flag}", "true")
        for port in set(c["public_ports"]) - set(b.get("public_ports", [])):
            f("container_port", "high", f"container {n} publishes {port} on all interfaces", f"{n}:{port}", port)
    return out


# ---- CVEs (OSV) --------------------------------------------------------------------------------------------------
def osv(url: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None, headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def osv_severity(v: dict) -> str:
    for s in v.get("severity") or []:
        if s.get("type") == "Ubuntu" and s.get("score"):
            return s["score"].lower()
    ds = (v.get("database_specific") or {}).get("severity") or ""
    return str(ds).lower()


def cves(host: str, pk: dict) -> list[dict]:
    """Only package names and versions leave the host (to api.osv.dev)."""
    eco = {"ubuntu": f"Ubuntu:{pk['version']}:LTS", "debian": f"Debian:{pk['version']}"}.get(pk["os"])
    if not eco:
        return []
    names = sorted(pk["list"])
    hits: dict[str, list[str]] = {}
    for i in range(0, len(names), 500):
        qs = [{"package": {"name": n, "ecosystem": eco}, "version": pk["list"][n]} for n in names[i:i + 500]]
        res = osv("https://api.osv.dev/v1/querybatch", {"queries": qs})
        for n, r in zip(names[i:i + 500], res.get("results", [])):
            if r.get("vulns"):
                hits[n] = [v["id"] for v in r["vulns"]]
    cache_p = os.path.join(STATE, "osv_cache2.json")
    cache = load(cache_p, {})
    out = []
    for n, ids in hits.items():
        bad = []
        for vid in ids:
            if vid not in cache:
                try:
                    v = osv(f"https://api.osv.dev/v1/vulns/{vid}")
                    # a fix counts only for this release: a "fixed" event under another ecosystem is not an upgrade here
                    fixed = sorted({a["package"]["ecosystem"] for a in v.get("affected", []) for r in a.get("ranges", [])
                                    for e in r.get("events", []) if e.get("fixed") and a.get("package")})
                    cache[vid] = {"sev": osv_severity(v), "fixed_in": fixed, "cve": next((u for u in v.get("upstream", []) + v.get("aliases", []) if u.startswith("CVE-")), vid)}
                except Exception:
                    continue
            c = cache[vid]
            if c["sev"] in ("medium", "high", "critical") and eco in c.get("fixed_in", []):
                bad.append(c)
        if bad:
            worst = max(bad, key=lambda c: SEV.get(c["sev"], 0))["sev"]
            ids_s = ", ".join(sorted({c["cve"] for c in bad})[:4]) + (" …" if len(bad) > 4 else "")
            out.append({"finding_id": fid(host, "cve", n, pk["list"][n]), "host": host, "check": "cve", "severity": worst,
                        "title": f"{n} {pk['list'][n]}: {len(bad)} CVE{'s' if len(bad) > 1 else ''} up to {worst}, fix available ({ids_s})",
                        "subject": n, "value": pk["list"][n], "baseline_value": "", "detail": f"OSV {eco}; upgrade the package"})
    save(cache_p, cache)
    return out


# ---- decisions from the vault ------------------------------------------------------------------------------------
def app_call(path: str, method: str = "GET"):
    ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(APP + path, method=method, headers={"Host": APP_HOST}, data=b"{}" if method == "POST" else None)
    with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
        return json.load(r)


def fold(base: dict, seen: set, fnd: dict, snap: dict) -> None:
    """An 'expected' decision: the current value becomes the baseline for that subject."""
    c, s = fnd["check"], fnd["subject"]
    if c in ("port_new", "port_gone"):
        base["ports"] = [p for p in base["ports"] if f"{p['proto']} {p['addr']}:{p['port']}" != s] + \
                        [p for p in snap["ports"] if f"{p['proto']} {p['addr']}:{p['port']}" == s]
    elif c in ("file_added", "file_changed", "file_removed"):
        base["files"].pop(s, None)
        if s in snap["files"]:
            base["files"][s] = snap["files"][s]
    elif c == "unit_new":
        base["units"] = sorted(set(base["units"]) | {s})
    elif c in ("ssh_new_source",):
        seen.add(s)
    elif c in ("container_new", "container_risk", "container_port"):
        n = s.split(":")[0]
        base["containers"] = [x for x in base["containers"] if cname(x["name"]) != n] + [x for x in snap["containers"] if cname(x["name"]) == n]


# ---- publish -----------------------------------------------------------------------------------------------------
def publish(findings: list[dict], sweeps: list[dict]) -> None:
    import boto3, pyarrow as pa, pyarrow.parquet as pq
    from publish_s3 import env
    env()
    s3 = boto3.client("s3", endpoint_url=os.environ.get("MOSCA_S3_ENDPOINT", "http://127.0.0.1:9000"), region_name="us-east-1",
                      aws_access_key_id=os.environ["MOSCA_S3_ACCESS_KEY"], aws_secret_access_key=os.environ["MOSCA_S3_SECRET_KEY"])
    bucket = os.environ.get("MOSCA_S3_BUCKET", "mosca")
    for name, rows, cols in (("findings", findings, ["finding_id", "host", "check", "severity", "title", "subject", "value", "baseline_value",
                                                      "detail", "status", "first_seen", "last_seen", "snapshot_sha256"]),
                             ("sweeps", sweeps, ["host", "sweep_time", "probe_s", "ports", "files", "units", "containers", "packages",
                                                 "auth_failed", "auth_accepted", "open_findings", "snapshot_sha256", "cve_checked_at", "baseline_set"])):
        types = {c: pa.float64() if c == "probe_s" else pa.int64() if c in ("ports", "files", "units", "containers", "packages", "auth_failed",
                 "auth_accepted", "open_findings") else pa.string() for c in cols}
        t = pa.table({c: [r.get(c) for r in rows] for c in cols}, schema=pa.schema([(c, types[c]) for c in cols]))
        buf = io.BytesIO(); pq.write_table(t, buf, compression="zstd")
        s3.put_object(Bucket=bucket, Key=f"sentinel/current/{name}/{name}.parquet", Body=buf.getvalue(), ContentType="application/vnd.apache.parquet",
                      Metadata={"rows": str(len(rows)), "written": now()})


def main(argv: list[str]) -> int:
    from common import targets
    remote = "--remote" in argv
    hosts = [h for h in targets().get("sentinel", []) if bool(h.get("local")) != remote]
    store_p = os.path.join(STATE, "findings.json")
    store: dict = load(store_p, {})
    sweeps_p = os.path.join(STATE, "sweeps.json")
    sweeps: dict = load(sweeps_p, {})
    try:
        decided = {d["finding_id"]: d["decision"] for d in app_call("/sentinel/decisions")}
    except Exception as e:
        decided = {}
        print("vault decisions unavailable:", type(e).__name__, file=sys.stderr)
    for h in hosts:
        name = h["name"]
        hdir = os.path.join(STATE, name)
        try:
            snap = snapshot(h)
        except Exception as e:
            print(name, "probe failed:", type(e).__name__, str(e)[:120], file=sys.stderr)
            continue
        raw = json.dumps(snap, sort_keys=True).encode()
        sha = hashlib.sha256(raw).hexdigest()
        os.makedirs(hdir, exist_ok=True)
        with open(os.path.join(hdir, f"{snap['time']}.json"), "wb") as fh:
            fh.write(raw)
        for p in os.listdir(hdir):                      # keep a week of snapshots
            if p.endswith("Z.json") and os.path.getmtime(os.path.join(hdir, p)) < time.time() - 7 * 86400:
                os.remove(os.path.join(hdir, p))
        base_p, seen_p = os.path.join(hdir, "baseline.json"), os.path.join(hdir, "seen_sources.json")
        base, seen = load(base_p, None), set(load(seen_p, []))
        first = base is None
        if first:
            base = {k: snap[k] for k in ("ports", "files", "units", "containers")}
            seen = {a["src"] for a in snap["auth"]["accepted"]}
        # fold decisions taken in the vault since the last sweep
        for k, fnd in list(store.items()):
            if fnd["host"] == name and fnd["status"] == "open" and decided.get(k):
                fnd["status"] = decided[k]
                if decided[k] == "expected":
                    fold(base, seen, fnd, snap)
        cur = [] if first else diff(name, base, snap, seen)
        sw = sweeps.get(name, {})
        if "--cves" in argv or snap["packages"]["sha256"] != sw.get("packages_sha") or time.time() - sw.get("cve_t", 0) > CVE_EVERY_S:
            try:
                sw["cves"] = cves(name, snap["packages"]); sw["cve_t"] = time.time(); sw["packages_sha"] = snap["packages"]["sha256"]
            except Exception as e:
                print(name, "OSV check failed:", type(e).__name__, str(e)[:120], file=sys.stderr)
        cur += sw.get("cves", [])
        ids = set()
        for x in cur:
            ids.add(x["finding_id"])
            old = store.get(x["finding_id"])
            if old and old["status"] != "open":
                continue                                # decided: stays decided
            store[x["finding_id"]] = {**x, "status": "open", "first_seen": old["first_seen"] if old else snap["time"], "last_seen": snap["time"],
                                      "snapshot_sha256": sha}
        for k, fnd in store.items():                    # a state finding that went back to the baseline resolves itself
            if fnd["host"] == name and fnd["status"] == "open" and k not in ids and not fnd["check"].startswith("ssh_"):
                fnd["status"] = "resolved"; fnd["last_seen"] = snap["time"]
        for a in snap["auth"]["accepted"]:
            if decided.get(fid(name, "ssh_new_source", a["src"], a["user"])) == "expected":
                seen.add(a["src"])
        save(base_p, base); save(seen_p, sorted(seen))
        sw.update({"host": name, "sweep_time": snap["time"], "probe_s": snap["probe_s"], "ports": len(snap["ports"]), "files": len(snap["files"]),
                   "units": len(snap["units"]), "containers": len(snap["containers"]), "packages": len(snap["packages"]["list"]),
                   "auth_failed": sum(snap["auth"]["failed"].values()), "auth_accepted": len(snap["auth"]["accepted"]),
                   "open_findings": sum(1 for f in store.values() if f["host"] == name and f["status"] == "open"), "snapshot_sha256": sha,
                   "cve_checked_at": datetime.fromtimestamp(sw.get("cve_t", 0), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if sw.get("cve_t") else "",
                   "baseline_set": "this sweep" if first else sw.get("baseline_set") or snap["time"]})
        sweeps[name] = sw
        print(name, "sweep", snap["time"], "open", sw["open_findings"], "new" if first else "", f"{snap['probe_s']}s")
    cutoff = time.time() - 7 * 86400                    # resolved / decided findings drop off after a week
    store = {k: v for k, v in store.items() if v["status"] == "open" or datetime.strptime(v["last_seen"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp() > cutoff}
    save(store_p, store); save(sweeps_p, sweeps)
    publish(sorted(store.values(), key=lambda f: (-SEV.get(f["severity"], 0), f["first_seen"])),
            [{k: v for k, v in s.items() if k not in ("cves", "cve_t", "packages_sha")} for s in sweeps.values()])
    try:
        app_call("/sentinel/ping", "POST")
    except Exception as e:
        print("app ping failed:", type(e).__name__, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
