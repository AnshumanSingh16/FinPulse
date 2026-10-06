from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Liveness: the process is up and serving HTTP. Does not touch dependencies."""

    status: Literal["ok"]
    service: str
    version: str
    environment: str
    timestamp: datetime


class DependencyCheck(BaseModel):
    name: str
    status: Literal["ok", "failed"]
    latency_ms: float | None = None
    detail: str | None = Field(
        default=None, description="Why the check failed. Never contains credentials."
    )


class ReadinessResponse(BaseModel):
    """Readiness: whether the service can do useful work right now."""

    status: Literal["ready", "not_ready"]
    checks: list[DependencyCheck]
