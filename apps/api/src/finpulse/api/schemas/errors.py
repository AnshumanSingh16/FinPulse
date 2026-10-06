from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class FieldError(BaseModel):
    loc: list[str | int]
    msg: str
    type: str


class ProblemDetails(BaseModel):
    """RFC 7807 error body, returned with ``Content-Type: application/problem+json``."""

    type: str = Field(description="URI identifying the error type")
    title: str
    status: int
    code: str = Field(description="Stable machine-readable error code")
    detail: str | None = None
    request_id: str | None = None
    errors: list[FieldError] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)
