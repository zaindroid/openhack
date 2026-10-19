"""Runtime settings, all from the environment. Nothing here is domain-specific."""
from __future__ import annotations
import os
from dataclasses import dataclass


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    return v if v not in (None, "") else default


@dataclass
class Settings:
    app_name: str = _env("APP_NAME", "whycore-app")
    # data: zetaris (prod) | postgres (dev) | duckdb (demo, seed CSVs)
    data_backend: str = _env("DATA_BACKEND", "duckdb")
    zetaris_rest: str | None = _env("ZETARIS_REST")
    zetaris_user: str | None = _env("ZETARIS_USER")
    zetaris_password: str | None = _env("ZETARIS_PASSWORD")
    zetaris_prefix: str = _env("ZETARIS_PREFIX", "")            # e.g. "kessler_pg." so table names resolve in Zetaris
    database_url: str = _env("DATABASE_URL", "postgresql://app:app@localhost:5432/app")
    seed_dir: str = _env("SEED_DIR", "app/data/seed")
    schema_file: str = _env("SCHEMA_FILE", "app/schema.sql")
    # model: Meterless (OpenAI-compatible) → Nemotron; offline templater when unset
    model_base_url: str | None = _env("MODEL_BASE_URL")
    model_api_key: str = _env("MODEL_API_KEY", "")
    model_reason: str = _env("MODEL_REASON", "nvidia/nemotron-3.5-super-vl-120b-a12b")
    model_fast: str = _env("MODEL_FAST", "nvidia/nemotron-3-nano")
    meterless_app: str = _env("METERLESS_APP", _env("APP_NAME", "whycore-app"))
    memory_dir: str = _env("MEMORY_DIR", "data/memory")
    max_signals: int = int(_env("MAX_SIGNALS", "5"))
    port: int = int(_env("PORT", "8080"))


settings = Settings()
