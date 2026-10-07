"""Runtime configuration, read once from the environment.

Values come from process environment variables first, then from the repository-root ``.env``
file (the same file the web app reads), so local development has a single place to configure.
Nothing in here has a secret default.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[4]

Environment = Literal["development", "test", "staging", "production"]
LogFormat = Literal["json", "console"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",  # the shared .env also holds web-only variables
        frozen=True,
    )

    env: Environment = Field(default="development", validation_alias="FINPULSE_ENV")

    api_host: str = Field(default="127.0.0.1", validation_alias="API_HOST")
    api_port: int = Field(default=8000, ge=1, le=65535, validation_alias="API_PORT")
    cors_allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"],
        validation_alias="CORS_ALLOWED_ORIGINS",
    )

    log_level: LogLevel = Field(default="INFO", validation_alias="LOG_LEVEL")
    log_format: LogFormat = Field(default="json", validation_alias="LOG_FORMAT")

    # Matches infra/docker-compose.yml so `make db-up` works without editing anything.
    database_url: str = Field(
        default="postgresql+psycopg://finpulse:finpulse@localhost:5432/finpulse",
        validation_alias="DATABASE_URL",
    )
    database_pool_size: int = Field(default=5, ge=1, le=50, validation_alias="DATABASE_POOL_SIZE")
    database_connect_timeout_s: float = Field(
        default=3.0, gt=0, le=30, validation_alias="DATABASE_CONNECT_TIMEOUT_S"
    )

    # --- AI agents (Claude). Optional: without credentials the deterministic API works and the
    # agent endpoints answer 503 llm_unavailable. The key is never logged or returned.
    anthropic_api_key: SecretStr | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")
    llm_model: str = Field(default="claude-opus-5-5", validation_alias="LLM_MODEL")
    llm_effort: Literal["low", "medium", "high", "xhigh", "max"] = Field(
        default="high", validation_alias="LLM_EFFORT"
    )
    llm_max_tokens: int = Field(default=16000, ge=1024, le=64000, validation_alias="LLM_MAX_TOKENS")
    llm_timeout_s: float = Field(default=300.0, gt=0, le=1800, validation_alias="LLM_TIMEOUT_S")
    llm_max_retries: int = Field(default=2, ge=0, le=10, validation_alias="LLM_MAX_RETRIES")
    # Server-side refusal fallback (Claude API only): a declined request is retried on the model
    # Anthropic recommends for the refusal category.
    llm_refusal_fallback: bool = Field(default=True, validation_alias="LLM_REFUSAL_FALLBACK")

    # Investigations kept for inspection (GET /api/v1/investigations); optionally also written
    # as JSON files to this directory.
    investigations_keep: int = Field(
        default=50, ge=1, le=1000, validation_alias="INVESTIGATIONS_KEEP"
    )
    investigations_dir: Path | None = Field(default=None, validation_alias="INVESTIGATIONS_DIR")

    # --- Security (SECURITY.md). API keys as name:role:sha256hex[:org_uuid], comma-separated;
    # generate with `finpulse auth new-key`. Required outside development and test.
    api_keys: SecretStr | None = Field(default=None, validation_alias="API_KEYS")
    # Running investigations per organisation (each makes several paid LLM calls).
    investigations_max_running: int = Field(
        default=2, ge=1, le=50, validation_alias="INVESTIGATIONS_MAX_RUNNING"
    )
    max_request_bytes: int = Field(
        default=1_000_000, ge=1024, le=50_000_000, validation_alias="MAX_REQUEST_BYTES"
    )
    # Where the AI investigation audit trail is written. "memory" is for tests and local runs
    # without a database; staging and production must use "postgres".
    audit_backend: Literal["postgres", "memory"] = Field(
        default="postgres", validation_alias="AUDIT_BACKEND"
    )

    # The deterministic demo (docs/DEMO.md): a scripted stand-in for the agents and a reset
    # endpoint. Never available in production.
    demo_enabled: bool = Field(default=True, validation_alias="DEMO_ENABLED")
    # Seconds × a per-agent factor the scripted agents wait, so the live timeline is watchable.
    demo_script_pace: float = Field(default=1.0, ge=0, le=10, validation_alias="DEMO_SCRIPT_PACE")

    @property
    def demo_allowed(self) -> bool:
        return self.demo_enabled and self.env != "production"

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @field_validator("database_url")
    @classmethod
    def _normalise_database_url(cls, value: str) -> str:
        # Supabase and most hosts hand out plain ``postgres://`` / ``postgresql://`` URLs;
        # SQLAlchemy needs the driver named explicitly.
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                return "postgresql+psycopg://" + value.removeprefix(prefix)
        if not value.startswith("postgresql+psycopg://"):
            raise ValueError("DATABASE_URL must be a PostgreSQL URL (postgresql://…)")
        return value

    @model_validator(mode="after")
    def _production_guards(self) -> Settings:
        if self.env == "production" and "*" in self.cors_allowed_origins:
            raise ValueError("CORS_ALLOWED_ORIGINS may not contain '*' in production")
        return self

    @property
    def is_development(self) -> bool:
        return self.env == "development"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
