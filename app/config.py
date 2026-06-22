"""Application configuration via environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── Devin ──────────────────────────────────────────────────────────────────
    devin_api_key: str

    # ── GitHub ─────────────────────────────────────────────────────────────────
    github_token: str
    github_webhook_secret: str
    github_owner: str
    github_repo: str

    # ── Database ────────────────────────────────────────────────────────────────
    database_url: str = (
        "postgresql+asyncpg://devin:devin@localhost:5432/devin_orchestrator"
    )
    database_url_ro: str = (
        "postgresql+asyncpg://analytics_ro:analytics_ro_pass@localhost:5432/devin_orchestrator"
    )

    # ── Tunables ───────────────────────────────────────────────────────────────
    # Set to true when using `gh webhook forward` locally (it signs with its own secret)
    skip_webhook_signature: bool = False
    app_env: str = "development"
    max_acu_limit: int = 50
    max_attempts: int = 3
    auto_remediate_label: str = "devin:auto-remediate"
    analytics_row_limit: int = 500
    analytics_timeout_ms: int = 10_000
    poll_interval_seconds: int = 30


settings = Settings()
