"""Run memory. Local JSON files are authoritative; every record is mirrored into Meterless H-MEM (the open engine,
vendored unmodified in whycore/meterless/engines/hmem and served by whycore/meterless/server.ts on
METERLESS_ENGINES_URL) when that sidecar is up.

What is remembered: per (domain, signal fingerprint) the hypotheses that were REJECTED and why. A warm run skips
them, which is the 'steps cold vs warm' metric in the evals.

H-MEM mirror: remember() adds one canonical H-MEM record per new rejection (type factual, layer long_term, tags
fp:<fingerprint> hyp:<id> app:<METERLESS_APP>, provenance plan_run); recall() falls back to H-MEM records by tag when
the local file has nothing for a fingerprint; reset() deletes this app's records (the engine's append-only ledger keeps
the history). When the sidecar is unreachable the mirror is off for 60 s and stats() says so; nothing else changes."""
from __future__ import annotations
import hashlib, json, os, time
from whycore.settings import settings


class HMemMirror:
    def __init__(self, url: str | None) -> None:
        self.url = (url or "").rstrip("/")
        self.down_until = 0.0
        self.errors = 0

    def _call(self, method: str, path: str, **kw):
        if not self.url or time.time() < self.down_until:
            return None
        import httpx
        try:
            r = httpx.request(method, self.url + path, timeout=2.0, **kw)
            r.raise_for_status()
            return r.json()
        except Exception:
            self.errors += 1
            self.down_until = time.time() + 60
            return None

    def add(self, fp: str, hyp: str, reason: str) -> None:
        self._call("POST", "/hmem/add", json={
            "content": f"{settings.meterless_app}: hypothesis {hyp} rejected for {fp}: {reason}",
            "type": "factual", "layer": "long_term", "confidence": 0.9, "source": f"whycore:{settings.meterless_app}",
            "tags": [f"fp:{fp}", f"hyp:{hyp}", f"app:{settings.meterless_app}"],
            "provenance": {"origin": "plan_run", "learnedAt": int(time.time() * 1000), "label": f"Skeptic rejection ({hyp})"}})

    def recall(self, fp: str) -> dict:
        recs = self._call("GET", "/hmem/records", params={"tag": f"fp:{fp}"}) or []
        out = {}
        for r in recs:
            hyp = next((t[4:] for t in r.get("tags", []) if t.startswith("hyp:")), None)
            if hyp:
                out[hyp] = r["content"].split(": ", 2)[-1]
        return out

    def reset(self) -> None:
        self._call("POST", "/hmem/delete", json={"tag": f"app:{settings.meterless_app}", "reason": "whycore memory reset"})

    def stats(self) -> dict:
        if not self.url:
            return {"enabled": False}
        js = self._call("GET", "/hmem/stats")
        return {"enabled": True, "url": self.url, "online": js is not None, "errors": self.errors, **(js or {})}


class Memory:
    def __init__(self, path: str | None = None) -> None:
        self.dir = path or settings.memory_dir
        self.runs = os.path.join(self.dir, "runs.jsonl")
        self.rejections = os.path.join(self.dir, "rejections.json")
        self.hmem = HMemMirror(settings.meterless_engines_url)

    def _ensure(self) -> None:
        os.makedirs(self.dir, exist_ok=True)

    @staticmethod
    def fingerprint(domain: str, signal_id: str, signal_props: dict) -> str:
        """Per signal by default. A domain that wants memory to generalise across similar signals sets
        props["memory_key"] (e.g. the region or asset class); then all signals with that key share rejections."""
        key = signal_props.get("memory_key") or signal_id
        return hashlib.sha1(f"{domain}|{key}".encode()).hexdigest()[:12]

    def recall(self, fp: str) -> dict:
        if os.path.exists(self.rejections):
            with open(self.rejections) as f:
                local = json.load(f).get(fp, {})
            if local:
                return local
        return self.hmem.recall(fp)

    def remember(self, fp: str, rejected: dict[str, str]) -> None:
        self._ensure()
        store = {}
        if os.path.exists(self.rejections):
            with open(self.rejections) as f:
                store = json.load(f)
        cur = store.get(fp, {})
        for hyp, reason in rejected.items():
            if hyp not in cur:
                self.hmem.add(fp, hyp, reason)
        cur.update(rejected)
        store[fp] = cur
        with open(self.rejections, "w") as f:
            json.dump(store, f, indent=1)

    def log_run(self, record: dict) -> None:
        self._ensure()
        with open(self.runs, "a") as f:
            f.write(json.dumps({"t": time.time(), **record}) + "\n")

    def stats(self) -> dict:
        n = 0
        if os.path.exists(self.runs):
            with open(self.runs) as f:
                n = sum(1 for _ in f)
        rej = 0
        if os.path.exists(self.rejections):
            with open(self.rejections) as f:
                rej = sum(len(v) for v in json.load(f).values())
        return {"runs": n, "remembered_rejections": rej, "dir": self.dir, "hmem": self.hmem.stats()}

    def reset(self) -> None:
        for p in (self.runs, self.rejections):
            if os.path.exists(p):
                os.remove(p)
        self.hmem.reset()


memory = Memory()
