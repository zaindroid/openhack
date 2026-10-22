"""Public, read-only view of Mosca (mosca-public.zaindroid.me, no Cloudflare Access).

It never talks to the outside world for the app: it subscribes to the private app's event stream (UPSTREAM/events, on
the internal network), pseudonymises every event and serves the result. There is no POST, PUT or DELETE route, so a
visitor cannot start a run, approve an action or reset memory; the private app at mosca.zaindroid.me stays behind Access.

What is removed or replaced before anything leaves this process:
  - host names, domains, IPv4/IPv6 addresses, e-mail addresses, home directories and secret file names → stable
    pseudonyms (ssh-1, tls-4, domain-2, ip-3, …), numbered in inventory order so they are the same in every run;
  - SQL text, raw scan properties and run details beyond the label, verdicts and first draft action.
Counts, verdicts, timings, model names and the agent flow are passed through unchanged, so the view is the real run.

GET /            the live page (whycore/static/live.html, with Run replaced by Replay)
GET /events      pseudonymised live event stream (SSE)
GET /replay      the last finished run's events, for the Replay button
GET /meta        title, question, description, sources, backend, model
GET /runs/{id}   label, verdicts and first action per result, for a run this process recorded
GET /healthz
"""
from __future__ import annotations
import json, os, queue, re, threading, time

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse

UPSTREAM = os.environ.get("UPSTREAM", "http://lab-mosca:8080").rstrip("/")
LIVE_HTML = os.environ.get("LIVE_HTML", "/srv/live.html")
MAX_SUBS = int(os.environ.get("MAX_SUBSCRIBERS", "200"))
KEEP_PUBLIC = {"csrc.nist.gov", "nist.gov", "crt.sh", "openssh.com", "libssh.org", "github.com"}
DROP = {"sql", "sql_executed", "props", "data", "note", "host", "path", "question_sql"}

app = FastAPI(title="mosca public view", docs_url=None, redoc_url=None, openapi_url=None)


# ---------- pseudonyms ------------------------------------------------------------------------------------------------
class Pseudonyms:
    DOMAIN = re.compile(r"(?i)\b(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,24}\b")
    IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
    IPV6 = re.compile(r"(?i)\b(?:[0-9a-f]{1,4}:){3,7}[0-9a-f]{1,4}\b")
    EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
    HOME = re.compile(r"/(?:home|Users)/[^/\s,;]+")
    SECRET = re.compile(r"(?i)\b(secrets?/)[^\s,;]+")
    KIND = {"ssh": "ssh", "tls": "tls", "ct_cert": "cert", "repo_key": "key", "firmware": "fw"}

    def __init__(self) -> None:
        self.words: dict[str, str] = {}     # exact strings → pseudonym, longest replaced first
        self.auto: dict[str, str] = {}      # domains/IPs seen only in events, numbered on first sight
        self.lock = threading.Lock()
        self.loaded = 0.0

    def load(self) -> None:
        """Names from the private app's inventory view, numbered per kind in asset_id order."""
        rows = httpx.get(f"{UPSTREAM}/view/inventory", timeout=120).json()
        cols, n, words = rows["columns"], {}, {}
        for r in rows["rows"]:
            r = dict(zip(cols, r)) if isinstance(r, list) else r
            name, kind = str(r.get("name") or ""), str(r.get("kind") or "asset")
            if not name or name in words:
                continue
            k = self.KIND.get(kind, kind)
            n[k] = n.get(k, 0) + 1
            words[name] = f"{k}-{n[k]}"
            # bare host names inside a name ("SSH servingz", "SSH ged25-ki (rtx5090)") have no dot, so the regexes
            # below would miss them: every token of an SSH/TLS name that is not a plain word is a host name.
            for tok in re.split(r"[\s()]+", name):
                if tok and tok.lower() not in {"ssh", "edge", "tls", "ct:", "key", "file", "public", "firmware"} and \
                        (kind in ("ssh", "tls") or re.search(r"[\d._/-]", tok)) and len(tok) > 2:
                    words.setdefault(tok, f"host-{len([v for v in words.values() if v.startswith('host-')]) + 1}")
        with self.lock:
            self.words = dict(sorted(words.items(), key=lambda kv: -len(kv[0])))
            self.loaded = time.time()

    def _auto(self, prefix: str, s: str) -> str:
        if s in self.auto:
            return self.auto[s]
        n = sum(1 for v in self.auto.values() if v.startswith(prefix + "-")) + 1
        self.auto[s] = f"{prefix}-{n}"
        return self.auto[s]

    def text(self, s: str) -> str:
        with self.lock:
            for w, p in self.words.items():
                if w in s:
                    s = s.replace(w, p)
            s = self.EMAIL.sub(lambda m: self._auto("email", m.group(0)), s)
            s = self.HOME.sub("/home/~", s)
            s = self.SECRET.sub(lambda m: m.group(1) + "…", s)
            s = self.IPV4.sub(lambda m: self._auto("ip", m.group(0)), s)
            s = self.IPV6.sub(lambda m: self._auto("ip", m.group(0)), s)
            s = self.DOMAIN.sub(lambda m: m.group(0) if self._public(m.group(0)) else self._auto("domain", m.group(0).lower()), s)
        return s

    @staticmethod
    def _public(d: str) -> bool:
        d = d.lower()
        if any(d == k or d.endswith("." + k) for k in KEEP_PUBLIC):
            return True
        # algorithm names look like domains (ecdsa-sha2-nistp256, x25519-sha256): keep tokens with no real TLD
        return d.rsplit(".", 1)[-1] in {"py", "yaml", "csv", "json", "sh", "txt", "md", "pem", "pub", "key"}

    def clean(self, v):
        if isinstance(v, str):
            return self.text(v)
        if isinstance(v, list):
            return [self.clean(x) for x in v]
        if isinstance(v, dict):
            return {k: self.clean(x) for k, x in v.items() if k not in DROP}
        return v


P = Pseudonyms()


# ---------- recorder: one upstream subscription, fanned out to visitors ----------------------------------------------
SUBS: list[queue.Queue] = []
SUBS_LOCK = threading.Lock()
RUNS: dict[str, dict] = {}            # run_id → {"events": [...], "run": trimmed run}
LAST = {"run_id": None}
_cur = {"run_id": None, "events": []}


def trim_run(r: dict, rid: str) -> dict:
    return {"run_id": rid, "summary": r.get("summary"),
            "results": [{"signal": {"label": x["signal"]["label"]},
                         "verdicts": [{"hypothesis_id": v["hypothesis_id"], "verdict": v["verdict"]} for v in x.get("verdicts", [])],
                         "actions": [{"label": a["label"]} for a in x.get("actions", [])[:1]]} for x in r.get("results", [])]}


def handle(ev: dict) -> None:
    if ev.get("type") == "run" and ev.get("status") == "running":
        _cur.update(run_id=ev.get("run_id"), events=[])
    if _cur["run_id"]:
        _cur["events"].append(ev)
    if ev.get("type") == "run" and ev.get("status") in ("done", "failed") and ev.get("run_id") == _cur["run_id"]:
        rid, evs = _cur["run_id"], _cur["events"]
        _cur.update(run_id=None, events=[])
        try:
            run = P.clean(trim_run(httpx.get(f"{UPSTREAM}/runs/{rid}", timeout=30).json(), rid))
        except Exception:
            run = None
        RUNS[rid] = {"events": evs, "run": run}
        for old in list(RUNS)[:-5]:
            RUNS.pop(old, None)
        if ev.get("status") == "done":
            LAST["run_id"] = rid


def recorder() -> None:
    while True:
        try:
            if time.time() - P.loaded > 600:
                P.load()
            with httpx.stream("GET", f"{UPSTREAM}/events", timeout=httpx.Timeout(10, read=60)) as r:
                for line in r.iter_lines():
                    if time.time() - P.loaded > 600:
                        threading.Thread(target=P.load, daemon=True).start()
                        P.loaded = time.time()
                    if not line.startswith("data: "):
                        continue
                    ev = P.clean(json.loads(line[6:]))
                    handle(ev)
                    with SUBS_LOCK:
                        subs = list(SUBS)
                    for q in subs:
                        try:
                            q.put_nowait(ev)
                        except queue.Full:
                            pass
        except Exception:
            time.sleep(3)


@app.on_event("startup")
def start() -> None:
    threading.Thread(target=recorder, daemon=True).start()


# ---------- routes ----------------------------------------------------------------------------------------------------
@app.get("/healthz")
def healthz():
    return {"ok": True, "names_loaded": bool(P.words), "visitors": len(SUBS), "last_run": LAST["run_id"]}


@app.get("/meta")
def meta():
    m = httpx.get(f"{UPSTREAM}/meta", timeout=30).json()
    model = m.get("model") or {}
    return P.clean({"name": m.get("name"), "title": m.get("title"), "question": m.get("question"), "description": m.get("description"),
                    "sources": [{k: s.get(k) for k in ("name", "access", "status")} for s in m.get("sources", [])],
                    "data_backend": m.get("data_backend"), "model": {"online": model.get("online"), "reason_model": model.get("reason_model")},
                    "public": True})


@app.get("/replay")
def replay():
    rid = LAST["run_id"]
    if not rid or rid not in RUNS:
        return {"run_id": None, "events": []}
    return {"run_id": rid, "events": RUNS[rid]["events"]}


@app.get("/runs/{run_id}")
def run(run_id: str):
    if run_id not in RUNS or not RUNS[run_id]["run"]:
        raise HTTPException(404, "no such run")
    return RUNS[run_id]["run"]


@app.get("/events")
def events():
    with SUBS_LOCK:
        if len(SUBS) >= MAX_SUBS:
            raise HTTPException(503, "too many viewers, try again shortly")
        q: queue.Queue = queue.Queue(maxsize=2000)
        SUBS.append(q)

    def gen():
        try:
            yield "retry: 2000\n\n"
            while True:
                try:
                    yield f"data: {json.dumps(q.get(timeout=15), default=str)}\n\n"
                except queue.Empty:
                    yield ": ping\n\n"
        finally:
            with SUBS_LOCK:
                if q in SUBS:
                    SUBS.remove(q)
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def page() -> str:
    s = open(LIVE_HTML, encoding="utf-8").read()
    for old, new in [
        ('<button class="btn" id="go">Run analysis</button>', '<button class="btn" id="go">Replay latest run</button>'),
        ('<a href="/">Open the full report</a>', 'Public read-only view: host names, addresses and file paths are pseudonymised; SQL is not shown.'),
        ("Waiting for events. Press Run analysis to start.", "Waiting for events. Press Replay latest run, or wait for the next scheduled run."),
        ("const Q = [];", "const Q = window.Q = [];"),
    ]:
        assert old in s, old
        s = s.replace(old, new)
    return s.replace("</body>", """<script>
$('#go').onclick = async () => {
  const r = await (await fetch('/replay')).json();
  if (!r.run_id) { feed('k', 'no finished run recorded yet; the next scheduled run will appear here live'); return; }
  $('#go').disabled = true; counters = {q:0, rows:0, sig:0, tests:0, sup:0, rej:0, model:0, sign:0}; paint();
  $('#cards').innerHTML = '<div class="k">replaying…</div>'; $('#feed').innerHTML = '';
  Object.values(NODES).forEach(n => n.g.querySelector('.badgeg').style.display = 'none');
  RUN_ID = r.run_id; feed('k', 'replay of run ' + r.run_id + ' (recorded as it happened)');
  window.Q.push(...r.events);
};
</script>
</body>""")


@app.get("/", response_class=HTMLResponse)
@app.get("/live", response_class=HTMLResponse)
def index():
    return page()
