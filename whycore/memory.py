"""Run memory. Local JSON files by default; the same records are what get mirrored into Meterless H-MEM when a key
is present (the pipeline calls remember()/recall(); swapping the store does not change the agents).

What is remembered: per (domain, signal fingerprint) the hypotheses that were REJECTED and why. A warm run skips
them, which is the 'steps cold vs warm' metric in the evals."""
from __future__ import annotations
import hashlib, json, os, time
from whycore.settings import settings


class Memory:
    def __init__(self, path: str | None = None) -> None:
        self.dir = path or settings.memory_dir
        self.runs = os.path.join(self.dir, "runs.jsonl")
        self.rejections = os.path.join(self.dir, "rejections.json")

    def _ensure(self) -> None:
        os.makedirs(self.dir, exist_ok=True)

    @staticmethod
    def fingerprint(domain: str, signal_id: str, signal_props: dict) -> str:
        """Per signal by default. A domain that wants memory to generalise across similar signals sets
        props["memory_key"] (e.g. the region or asset class); then all signals with that key share rejections."""
        key = signal_props.get("memory_key") or signal_id
        return hashlib.sha1(f"{domain}|{key}".encode()).hexdigest()[:12]

    def recall(self, fp: str) -> dict:
        if not os.path.exists(self.rejections):
            return {}
        with open(self.rejections) as f:
            return json.load(f).get(fp, {})

    def remember(self, fp: str, rejected: dict[str, str]) -> None:
        self._ensure()
        store = {}
        if os.path.exists(self.rejections):
            with open(self.rejections) as f:
                store = json.load(f)
        cur = store.get(fp, {})
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
        return {"runs": n, "remembered_rejections": rej, "dir": self.dir}

    def reset(self) -> None:
        for p in (self.runs, self.rejections):
            if os.path.exists(p):
                os.remove(p)


memory = Memory()
