"""Runtime configuration, read once from the environment.

Values come from process environment variables first, then from the repository-root ``.env``
file (the same file the web app reads), so local development has a single place to configure.
Nothing in here has a secret default.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
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
