"""Runtime settings for the agents, read from the environment (agents/.env in Compose). Names match agents/.env.example
and docs/GAMEPLAN.md. No secrets live here; the NVIDIA provider key is never an application variable."""
from __future__ import annotations
import os
from dataclasses import dataclass


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    return v if v not in (None, "") else default


def _flag(name: str, default: bool) -> bool:
    v = _env(name)
    return default if v is None else v.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Settings:
    # Zetaris: the only data path for agents (GAMEPLAN "win line")
    zetaris_rest_url: str | None = _env("ZETARIS_REST_URL")
    zetaris_org_id: str = _env("ZETARIS_ORG_ID", "1")
    zetaris_api_key: str | None = _env("ZETARIS_API_KEY")
    zetaris_user: str | None = _env("ZETARIS_USER")
    zetaris_password: str | None = _env("ZETARIS_PASSWORD")
    zetaris_mode: str = _env("ZETARIS_MODE", "auto")          # auto | live | fake   (fake = in-memory seed views, no network)
    zetaris_row_limit: int = int(_env("ZETARIS_ROW_LIMIT", "5000"))
    live_data: bool = _flag("FF_LIVE_DATA", False)            # floodsense.* instead of floodsense_seed.*

    # Nightshift (Meterless): every LLM call goes through one client on pinned lanes
    meterless_base_url: str | None = _env("METERLESS_BASE_URL")
    meterless_app: str = _env("METERLESS_APP", "floodsense-eu")
    meterless_scope: str = _env("METERLESS_SCOPE", "user")
    meterless_runtime_token: str = _env("METERLESS_RUNTIME_TOKEN", "") or ""
    model_fast: str = _env("MODEL_FAST", "nvidia/nemotron-3.5-lightning-30b-a3b")
    model_deep: str = _env("MODEL_DEEP", "nvidia/nemotron-3-super-120b-a12b")
    llm_timeout_s: float = float(_env("LLM_TIMEOUT_S", "180"))
    llm_mode: str = _env("LLM_MODE", "auto")                  # auto | live | fake   (fake = deterministic offline model)

    # Feature flags (defaults from agents/.env.example; a slipped increment stays behind its flag)
    ff_skeptic: bool = _flag("FF_SKEPTIC", True)
    ff_hitl: bool = _flag("FF_HITL", True)
    ff_judge: bool = _flag("FF_JUDGE", False)
    ff_hmem: bool = _flag("FF_HMEM", False)
    ff_rag_docs: bool = _flag("FF_RAG_DOCS", False)

    # Skeptic / Judge knobs
    skeptic_max_rounds: int = int(_env("SKEPTIC_MAX_ROUNDS", "3"))
    judge_repair_rounds: int = int(_env("JUDGE_REPAIR_ROUNDS", "1"))
    judge_min_score: float = float(_env("JUDGE_MIN_SCORE", "0.7"))      # proposal until the first eval run
    numeric_tolerance: float = float(_env("NUMERIC_TOLERANCE", "0.02"))  # 2 % relative, for numbers_match

    # HITL checkpointer: SQLite under the compose volume; memory when the directory is not writable
    checkpoint_dir: str = _env("CHECKPOINT_DIR", "/data/checkpoints")
    checkpointer: str = _env("CHECKPOINTER", "auto")          # auto | sqlite | memory

    # Agents service (internal to the compose network; the API proxies it)
    host: str = _env("AGENTS_HOST", "0.0.0.0")
    port: int = int(_env("AGENTS_PORT", "8100"))

    @property
    def schema(self) -> str:
        return "floodsense" if self.live_data else "floodsense_seed"


settings = Settings()
