"""Model access through Meterless (OpenAI-compatible, meterless-app header) → NVIDIA Nemotron.
Offline templater when MODEL_BASE_URL is unset so the deterministic pipeline runs end to end without a key.
The model only ever EXPLAINS; it never decides a verdict (those come from whycore.pipeline tests).

Nemotron 3.x/3.5 are reasoning models: with thinking on, a short max_tokens is spent entirely on hidden reasoning and
the answer comes back empty. MODEL_THINKING=off (default) sends chat_template_kwargs.enable_thinking=false.
`online` is true only when GET {MODEL_BASE_URL}/models answered 200 with this key (re-probed every 5 minutes), not
merely because a URL is configured."""
from __future__ import annotations
import json, logging, time
from whycore.settings import settings

log = logging.getLogger("whycore.model")
PROBE_TTL = 300


class Model:
    def __init__(self) -> None:
        self.configured = bool(settings.model_base_url)
        self.calls = 0
        self.tokens = 0
        self.failures = 0
        self.last_error: str | None = None
        self._probe_at = 0.0
        self._probe_ok = False
        if not self.configured:
            log.warning("MODEL_BASE_URL unset: offline templater. Set the Meterless endpoint for the real run.")

    @property
    def online(self) -> bool:
        if not self.configured:
            return False
        if time.time() - self._probe_at > PROBE_TTL:
            self._probe()
        return self._probe_ok

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {settings.model_api_key}", "meterless-app": settings.meterless_app, "meterless-scope": "user"}

    def _probe(self) -> None:
        import httpx
        self._probe_at = time.time()
        try:
            r = httpx.get(settings.model_base_url.rstrip("/") + "/models", headers=self._headers(), timeout=15)
            self._probe_ok = r.status_code == 200
            if not self._probe_ok:
                self.last_error = f"GET /models {r.status_code}"
        except Exception as e:
            self._probe_ok, self.last_error = False, f"GET /models {type(e).__name__}"

    def chat(self, system: str, user: str, *, deep: bool = True, json_mode: bool = False, max_tokens: int = 700) -> str:
        self.calls += 1
        if not self.configured:
            return self._offline(user, json_mode)
        import httpx
        model = settings.model_reason if deep else settings.model_fast
        body = {"model": model, "temperature": 0.2, "max_tokens": max_tokens,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if settings.model_thinking == "off":
            body["chat_template_kwargs"] = {"enable_thinking": False}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        try:
            r = httpx.post(settings.model_base_url.rstrip("/") + "/chat/completions", json=body, headers=self._headers(), timeout=180)
            r.raise_for_status()
        except Exception as e:
            self.failures += 1; self.last_error = f"{model}: {str(e)[:160]}"; self._probe_ok = False
            raise
        js = r.json()
        self.tokens += js.get("usage", {}).get("total_tokens", 0)
        self._probe_ok, self._probe_at = True, time.time()
        content = (js["choices"][0]["message"].get("content") or "").strip()
        if not content:
            self.failures += 1; self.last_error = f"{model}: empty content (finish_reason {js['choices'][0].get('finish_reason')})"
            raise RuntimeError(self.last_error)
        return content

    @staticmethod
    def _offline(user: str, json_mode: bool) -> str:
        if json_mode:
            return json.dumps({"note": "offline templater", "echo": user[:200]})
        # The pipeline passes a structured summary; echo it so the UI still reads as an explanation.
        return "[offline model] " + user

    def status(self) -> dict:
        return {"online": self.online, "configured": self.configured, "calls": self.calls, "tokens": self.tokens,
                "failures": self.failures, "last_error": self.last_error,
                "reason_model": settings.model_reason, "fast_model": settings.model_fast}


model = Model()
