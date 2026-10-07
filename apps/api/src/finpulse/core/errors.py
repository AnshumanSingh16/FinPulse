"""Domain error taxonomy.

Code anywhere in the backend raises these; ``finpulse.api.errors`` turns them into
RFC 7807 ``application/problem+json`` responses. Each error has a stable machine-readable
``code`` that clients may branch on, and an HTTP status.
"""

from __future__ import annotations

from typing import Any, ClassVar


class AppError(Exception):
    status: ClassVar[int] = 500
    code: ClassVar[str] = "internal_error"
    title: ClassVar[str] = "Internal error"

    def __init__(
        self,
        detail: str | None = None,
        *,
        code: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(detail or self.title)
        self.detail = detail
        # Instances may refine the class-level code, e.g. "subject_not_found".
        self.instance_code = code or self.code
        self.extra = extra or {}


class BadRequestError(AppError):
    status = 400
    code = "bad_request"
    title = "Bad request"


class UnauthorizedError(AppError):
    status = 401
    code = "unauthorized"
    title = "Authentication required"


class TooManyRequestsError(AppError):
    status = 429
    code = "too_many_requests"
    title = "Too many requests"


class ForbiddenError(AppError):
    status = 403
    code = "forbidden"
    title = "Forbidden"


class NotFoundError(AppError):
    status = 404
    code = "not_found"
    title = "Not found"


class ConflictError(AppError):
    status = 409
    code = "conflict"
    title = "Conflict"


class PreconditionFailedError(AppError):
    status = 412
    code = "precondition_failed"
    title = "Precondition failed"


class UnprocessableError(AppError):
    """Input is well-formed but the domain cannot act on it (e.g. insufficient history)."""

    status = 422
    code = "unprocessable"
    title = "Unprocessable request"


class DependencyUnavailableError(AppError):
    status = 503
    code = "dependency_unavailable"
    title = "Dependency unavailable"


class UpstreamLLMError(AppError):
    """The language model could not produce a usable answer (unavailable, refused, invalid)."""

    status = 502
    code = "llm_error"
    title = "AI layer error"


class LLMUnavailableError(UpstreamLLMError):
    status = 503
    code = "llm_unavailable"
    title = "AI layer unavailable"
