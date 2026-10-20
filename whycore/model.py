"""Model access, OpenAI-compatible, for two roles: `reason` (explanations) and `fast` (triage). The model only ever
EXPLAINS; it never decides a verdict (those come from whycore.pipeline tests). Offline templater when no endpoint is set.

Endpoint per role, first match wins:
  MODEL_<ROLE>_BASE_URL / MODEL_<ROLE>_API_KEY      different hosts per role (e.g. Nano on one GPU box, Super on another)
  <ROUTE>_<ROLE>_BASE_URL / <ROUTE>_<ROLE>_API_KEY  per-route, per-role
  <ROUTE>_BASE_URL / <ROUTE>_API_KEY                per-route single endpoint
  MODEL_BASE_URL / MODEL_API_KEY                    single endpoint (Meterless Nightshift hotspot or NVIDIA NIM)
Model id per role: MODEL_<ROLE> > <ROUTE>_<ROLE> > built-in default. ROUTE = MODEL_ROUTE (local | meterless | nim).
Fallback: when the primary fails after retries, MODEL_<ROLE>_FALLBACK (a model id) is tried on the MODEL_FALLBACK_ROUTE
route (default nim: NIM_BASE_URL, NIM_API_KEY). Every answer records which route, host and model produced it.

Calls retry 3 times with exponential backoff on timeouts, 429 and 5xx. Explanations are cached by sha256 of
(model, system, user) under MEMORY_DIR/explain_cache.json, so a re-run with the same evidence costs nothing.
Nemotron 3.x/3.5 are reasoning models; MODEL_THINKING=off (default) sends chat_template_kwargs.enable_thinking=false
(not on the meterless route, whose runtime picks the model). `online` is true only when GET /models answered 200 for
the reason endpoint or its fallback (re-probed every 5 minutes, and right after a failure)."""
from __future__ import annotations
import hashlib, json, logging, os, threading, time
from urllib.parse import urlparse
from whycore.settings import settings

log = logging.getLogger("whycore.model")
PROBE_TTL = 300
DEFAULT_MODEL = {"reason": "nvidia/nemotron-3.5-super-vl-120b-a12b", "fast": "nvidia/nemotron-3.5-lightning-30b-a3b"}
NIM_URL = "https://integrate.api.nvidia.com/v1"


def _env(name: str) -> str | None:
    v = os.environ.get(name)
    return v if v not in (None, "") else None


class Endpoint:
    def __init__(self, role: str, route: str | None, base: str | None, key: str, model: str) -> None:
        self.role, self.route, self.base, self.key, self.model = role, route or "default", (base or "").rstrip("/"), key, model
        self._probe_at, self._probe_ok, self.last_error = 0.0, False, None

    @property
    def host(self) -> str:
        return urlparse(self.base).netloc if self.base else ""

    def headers(self) -> dict:
        return {"Authorization": f"Bearer {self.key}", "meterless-app": settings.meterless_app, "meterless-scope": "user"}

    def online(self) -> bool:
        if not self.base:
            return False
        if time.time() - self._probe_at > PROBE_TTL:
            import httpx
            self._probe_at = time.time()
            try:
                r = httpx.get(self.base + "/models", headers=self.headers(), timeout=15)
                self._probe_ok = r.status_code == 200
                if not self._probe_ok:
                    self.last_error = f"GET /models {r.status_code}"
            except Exception as e:
                self._probe_ok, self.last_error = False, f"GET /models {type(e).__name__}"
        return self._probe_ok

    def mark(self, ok: bool, err: str | None = None) -> None:
        self._probe_ok = ok
        self._probe_at = time.time() if ok else 0.0       # a failure forces a fresh probe next time
        if err:
            self.last_error = err

    def describe(self) -> dict:
        return {"route": self.route, "host": self.host, "model": self.model, "online": self.online(), "last_error": self.last_error}


def resolve(role: str, route: str | None = None) -> Endpoint:
    R, ROLE = (route or _env("MODEL_ROUTE") or "").upper(), role.upper()
    pick = lambda *names: next((v for v in (_env(n) for n in names if n) if v), None)
    rn = lambda suffix: f"{R}_{suffix}" if R else None
    if route:   # an explicit route ignores the MODEL_* overrides (used by fallback and infra/model_hello.py)
        base = pick(rn(f"{ROLE}_BASE_URL"), rn("BASE_URL")) or (NIM_URL if R == "NIM" else None)
        key = pick(rn(f"{ROLE}_API_KEY"), rn("API_KEY")) or ""
        model = pick(rn(ROLE)) or DEFAULT_MODEL[role]
    else:
        base = pick(f"MODEL_{ROLE}_BASE_URL", rn(f"{ROLE}_BASE_URL"), rn("BASE_URL"), "MODEL_BASE_URL") or (NIM_URL if R == "NIM" else None)
        key = pick(f"MODEL_{ROLE}_API_KEY", rn(f"{ROLE}_API_KEY"), rn("API_KEY"), "MODEL_API_KEY") or ""
        model = pick(f"MODEL_{ROLE}", rn(ROLE)) or DEFAULT_MODEL[role]
    return Endpoint(role, (route or _env("MODEL_ROUTE") or ("single" if base else None)), base, key, model)


class ExplainCache:
    def __init__(self) -> None:
        self.path = os.path.join(settings.memory_dir, "explain_cache.json")
        self.lock = threading.Lock()
        self.hits = 0
        self._data: dict | None = None

    def _load(self) -> dict:
        if self._data is None:
            try:
                with open(self.path) as f:
                    self._data = json.load(f)
            except Exception:
                self._data = {}
        return self._data

    @staticmethod
    def key(model: str, system: str, user: str) -> str:
        return hashlib.sha256(json.dumps([model, system, user]).encode()).hexdigest()

    def get(self, k: str) -> dict | None:
        with self.lock:
            v = self._load().get(k)
            if v:
                self.hits += 1
            return v

    def put(self, k: str, v: dict) -> None:
        with self.lock:
            d = self._load(); d[k] = v
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(d, f)
            os.replace(tmp, self.path)

    def size(self) -> int:
        with self.lock:
            return len(self._load())


class Model:
    def __init__(self) -> None:
        self.ep = {r: resolve(r) for r in ("reason", "fast")}
        fb_route = _env("MODEL_FALLBACK_ROUTE") or "nim"
        self.fallback = {}
        for r in ("reason", "fast"):
            fm = _env(f"MODEL_{r.upper()}_FALLBACK")
            if fm:
                e = resolve(r, fb_route); e.model = fm
                if e.base and e.key:
                    self.fallback[r] = e
        self.configured = bool(self.ep["reason"].base)
        self.calls = self.tokens = self.failures = self.fallbacks = 0
        self.last_error: str | None = None
        self.cache = ExplainCache()
        self._lock = threading.Lock()
        if not self.configured:
            log.warning("no model endpoint configured: offline templater. Set MODEL_BASE_URL (or MODEL_ROUTE + its variables).")

    @property
    def online(self) -> bool:
        return self.configured and (self.ep["reason"].online() or ("reason" in self.fallback and self.fallback["reason"].online()))

    def _post(self, e: Endpoint, body: dict) -> dict:
        import httpx
        delay, last = 1.0, None
        for attempt in range(3):
            try:
                r = httpx.post(e.base + "/chat/completions", json=body, headers=e.headers(), timeout=settings.model_timeout_s)
                if r.status_code == 429 or r.status_code >= 500:
                    raise httpx.HTTPStatusError(f"HTTP {r.status_code}", request=r.request, response=r)
                r.raise_for_status()
                js = r.json()
                content = (js["choices"][0]["message"].get("content") or "").strip()
                if not content:
                    raise RuntimeError(f"empty content (finish_reason {js['choices'][0].get('finish_reason')})")
                return js
            except Exception as ex:
                last = ex
                status = getattr(getattr(ex, "response", None), "status_code", None)
                if status is not None and status < 500 and status != 429:
                    break                                          # 4xx other than 429: retrying will not help
                if attempt < 2:
                    time.sleep(delay); delay *= 2
        raise RuntimeError(f"{e.route}:{e.host}:{e.model}: {str(last)[:160]}")

    def answer(self, system: str, user: str, *, deep: bool = True, json_mode: bool = False, max_tokens: int = 700) -> tuple[str, dict]:
        """(text, meta) where meta says which route/host/model answered, latency, tokens, cache hit."""
        role = "reason" if deep else "fast"
        with self._lock:
            self.calls += 1
        if not self.configured:
            return self._offline(user, json_mode), {"route": "offline", "model": "offline templater", "ok": True, "cached": False}
        chain = [self.ep[role]] + ([self.fallback[role]] if role in self.fallback else [])
        errors = []
        for i, e in enumerate(chain):
            k = ExplainCache.key(e.model, system, user)
            hit = self.cache.get(k)
            if hit:
                return hit["text"], {**hit["meta"], "cached": True, "latency_ms": 0}
            body = {"model": e.model, "temperature": 0.2, "max_tokens": max_tokens,
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
            if settings.model_thinking == "off" and e.route != "meterless":
                body["chat_template_kwargs"] = {"enable_thinking": False}
            if json_mode:
                body["response_format"] = {"type": "json_object"}
            t0 = time.time()
            try:
                js = self._post(e, body)
            except Exception as ex:
                e.mark(False, str(ex)[:200]); errors.append(str(ex)[:200])
                continue
            e.mark(True)
            usage = js.get("usage", {}) or {}
            meta = {"route": e.route, "host": e.host, "model": js.get("model") or e.model, "ok": True, "fallback": i > 0,
                    "latency_ms": int((time.time() - t0) * 1000), "completion_tokens": usage.get("completion_tokens")}
            text = js["choices"][0]["message"]["content"].strip()
            with self._lock:
                self.tokens += usage.get("total_tokens", 0) or 0
                self.fallbacks += i > 0
            self.cache.put(k, {"text": text, "meta": meta})
            return text, {**meta, "cached": False}
        with self._lock:
            self.failures += 1
            self.last_error = " | ".join(errors)[:400]
        raise RuntimeError(self.last_error)

    def chat(self, system: str, user: str, *, deep: bool = True, json_mode: bool = False, max_tokens: int = 700) -> str:
        return self.answer(system, user, deep=deep, json_mode=json_mode, max_tokens=max_tokens)[0]

    @staticmethod
    def _offline(user: str, json_mode: bool) -> str:
        if json_mode:
            return json.dumps({"note": "offline templater", "echo": user[:200]})
        # The pipeline passes a structured summary; echo it so the UI still reads as an explanation.
        return "[offline model] " + user

    def status(self) -> dict:
        return {"online": self.online, "configured": self.configured, "calls": self.calls, "tokens": self.tokens,
                "failures": self.failures, "fallbacks": self.fallbacks, "last_error": self.last_error,
                "cache": {"entries": self.cache.size(), "hits": self.cache.hits},
                "reason_model": self.ep["reason"].model, "fast_model": self.ep["fast"].model,
                "endpoints": {r: e.describe() for r, e in self.ep.items()},
                "fallback": {r: e.describe() for r, e in self.fallback.items()}}


model = Model()
