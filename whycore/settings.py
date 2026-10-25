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
    # Names from the organisers' Participant Setup Guide (ZETARIS_REST_URL, ZETARIS_API_KEY, ZETARIS_USERNAME) are accepted
    # as aliases of ours. With ZETARIS_API_KEY set, the key is the bearer token and no login call is made.
    zetaris_rest: str | None = _env("ZETARIS_REST", _env("ZETARIS_REST_URL"))
    zetaris_user: str | None = _env("ZETARIS_USER", _env("ZETARIS_USERNAME"))
    zetaris_password: str | None = _env("ZETARIS_PASSWORD")
    zetaris_api_key: str | None = _env("ZETARIS_API_KEY")
    # optional password for everything reached through the Cloudflare edge (whycore/auth.py); off when empty
    app_password: str = _env("APP_PASSWORD", "")
    zetaris_prefix: str = _env("ZETARIS_PREFIX", "")            # e.g. "kessler_pg." so table names resolve in Zetaris
    # per-table sources, e.g. "assets=mosca_s3.assets,data_classes=mosca_pg.data_classes"; tables not listed get ZETARIS_PREFIX
    zetaris_tables: str = _env("ZETARIS_TABLES", "")
    zetaris_org_id: str = _env("ZETARIS_ORG_ID", "1")
    zetaris_limit: int = int(_env("ZETARIS_LIMIT", "100000"))   # Lightning caps rows per call at this limit
    database_url: str = _env("DATABASE_URL", "postgresql://app:app@localhost:5432/app")
    seed_dir: str = _env("SEED_DIR", "app/data/seed")
    schema_file: str = _env("SCHEMA_FILE", "app/schema.sql")
    # model: Meterless (OpenAI-compatible) → Nemotron; offline templater when unset
    model_base_url: str | None = _env("MODEL_BASE_URL")
    model_api_key: str = _env("MODEL_API_KEY", "")
    model_reason: str = _env("MODEL_REASON", "nvidia/nemotron-3.5-super-vl-120b-a12b")
    model_fast: str = _env("MODEL_FAST", "nvidia/nemotron-3.5-lightning-30b-a3b")
    model_thinking: str = _env("MODEL_THINKING", "off")         # off: chat_template_kwargs.enable_thinking=false (Nemotron)
    model_concurrency: int = int(_env("MODEL_CONCURRENCY", "8"))
    test_concurrency: int = int(_env("TEST_CONCURRENCY", "8"))         # signals tested in parallel (their SQL is independent)
    model_timeout_s: float = float(_env("MODEL_TIMEOUT_S", "60"))       # per call, before retry/fallback
    explain_budget_s: float = float(_env("EXPLAIN_BUDGET_S", "45"))     # whole explanation step of a run (edge cuts at 100 s)
    meterless_app: str = _env("METERLESS_APP", _env("APP_NAME", "whycore-app"))
    memory_dir: str = _env("MEMORY_DIR", "data/memory")
    meterless_engines_url: str | None = _env("METERLESS_ENGINES_URL")  # whycore/meterless/server.ts (H-MEM, World Model, Markovian)
    max_signals: int = int(_env("MAX_SIGNALS", "5"))
    port: int = int(_env("PORT", "8080"))
    # comma-separated "module:function" called with the finished Run (e.g. app.notary:sign_run)
    run_hooks: str = _env("RUN_HOOKS", "")


settings = Settings()
