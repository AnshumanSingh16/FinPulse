"""Map exceptions to RFC 7807 problem responses.

Domain errors (``AppError``), request validation errors and Starlette HTTP errors are handled
here. Unhandled exceptions are caught one level further out, in ``RequestContextMiddleware``,
so that they are logged with the request id and never leak a stack trace to the client.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import InterfaceError, OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from finpulse.api.schemas.errors import FieldError, ProblemDetails
from finpulse.core.errors import AppError
from finpulse.observability.logging import get_logger

PROBLEM_CONTENT_TYPE = "application/problem+json"
ERROR_TYPE_BASE = "https://finpulse.dev/errors/"

log = get_logger(__name__)


def problem_response(
    *,
    status: int,
    code: str,
    title: str,
    detail: str | None,
    request_id: str | None,
    errors: list[FieldError] | None = None,
    extra: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = ProblemDetails(
        type=ERROR_TYPE_BASE + code.replace("_", "-"),
        title=title,
        status=status,
        code=code,
        detail=detail,
        request_id=request_id,
        errors=errors or [],
        extra=extra or {},
    )
    response_headers = dict(headers or {})
    if request_id:
        response_headers["X-Request-ID"] = request_id
    return JSONResponse(
        status_code=status,
        content=jsonable_encoder(body),
        media_type=PROBLEM_CONTENT_TYPE,
        headers=response_headers,
    )


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


async def _handle_app_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)  # noqa: S101 - narrowed by registration
    emit = log.error if exc.status >= 500 else log.info
    emit("app_error", code=exc.instance_code, status=exc.status, detail=exc.detail)
    return problem_response(
        status=exc.status,
        code=exc.instance_code,
        title=exc.title,
        detail=exc.detail,
        request_id=_request_id(request),
        extra=exc.extra,
        headers={"WWW-Authenticate": "Bearer"} if exc.status == 401 else None,
    )


async def _handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)  # noqa: S101
    errors = [
        FieldError(loc=list(err.get("loc", ())), msg=err.get("msg", ""), type=err.get("type", ""))
        for err in exc.errors()
    ]
    return problem_response(
        status=422,
        code="validation_error",
        title="Request validation failed",
        detail=f"{len(errors)} field(s) failed validation.",
        request_id=_request_id(request),
        errors=errors,
    )


async def _handle_http_exception(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)  # noqa: S101
    try:
        phrase = HTTPStatus(exc.status_code).phrase
    except ValueError:
        phrase = "Error"
    code = {404: "route_not_found", 405: "method_not_allowed"}.get(
        exc.status_code, phrase.lower().replace(" ", "_").replace("-", "_")
    )
    detail = exc.detail if isinstance(exc.detail, str) and exc.detail != phrase else None
    return problem_response(
        status=exc.status_code,
        code=code,
        title=phrase,
        detail=detail,
        request_id=_request_id(request),
        headers=dict(exc.headers) if exc.headers else None,
    )


async def _handle_database_unavailable(request: Request, exc: Exception) -> JSONResponse:
    # Driver messages can include host names; log the type only and keep the response generic.
    log.warning("database_unavailable", error=type(exc).__name__)
    return problem_response(
        status=503,
        code="database_unavailable",
        title="Database unavailable",
        detail="The database could not be reached. Try again shortly.",
        request_id=_request_id(request),
        headers={"Retry-After": "5"},
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_exception_handler(OperationalError, _handle_database_unavailable)
    app.add_exception_handler(InterfaceError, _handle_database_unavailable)
