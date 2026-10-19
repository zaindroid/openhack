"""Model access through Meterless (OpenAI-compatible, meterless-app header) → NVIDIA Nemotron.
Offline templater when MODEL_BASE_URL is unset so the deterministic pipeline runs end to end without a key.
The model only ever EXPLAINS; it never decides a verdict (those come from whycore.pipeline tests)."""
from __future__ import annotations
import json, logging
from whycore.settings import settings

log = logging.getLogger("whycore.model")


class Model:
    def __init__(self) -> None:
        self.online = bool(settings.model_base_url)
        self.calls = 0
        self.tokens = 0
        if not self.online:
            log.warning("MODEL_BASE_URL unset: offline templater. Set the Meterless endpoint for the real run.")

    def chat(self, system: str, user: str, *, deep: bool = True, json_mode: bool = False, max_tokens: int = 700) -> str:
        self.calls += 1
        if not self.online:
            return self._offline(user, json_mode)
        import httpx
        model = settings.model_reason if deep else settings.model_fast
        headers = {"Authorization": f"Bearer {settings.model_api_key}", "meterless-app": settings.meterless_app, "meterless-scope": "user"}
        body = {"model": model, "temperature": 0.2, "max_tokens": max_tokens,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        r = httpx.post(settings.model_base_url.rstrip("/") + "/chat/completions", json=body, headers=headers, timeout=180)
        r.raise_for_status()
        js = r.json()
        self.tokens += js.get("usage", {}).get("total_tokens", 0)
        return js["choices"][0]["message"]["content"]

    @staticmethod
    def _offline(user: str, json_mode: bool) -> str:
        if json_mode:
            return json.dumps({"note": "offline templater", "echo": user[:200]})
        # The pipeline passes a structured summary; echo it so the UI still reads as an explanation.
        return "[offline model] " + user

    def status(self) -> dict:
        return {"online": self.online, "calls": self.calls, "tokens": self.tokens,
                "reason_model": settings.model_reason, "fast_model": settings.model_fast}


model = Model()
