"""Request context: correlation id, access logging and the last-resort error handler.

Written as plain ASGI middleware (not ``BaseHTTPMiddleware``) so it adds no task hops and works
unchanged for streaming responses such as the SSE endpoints planned for investigations.
"""

from __future__ import annotations

import re
import time
import uuid

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from finpulse.api.errors import problem_response
from finpulse.observability.logging import get_logger

REQUEST_ID_HEADER = "x-request-id"
# Accept a caller-supplied id only if it is short and boring; otherwise mint our own.
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._\-]{1,128}$")

log = get_logger("finpulse.access")


def new_request_id() -> str:
    return f"req_{uuid.uuid4().hex}"


def _incoming_request_id(scope: Scope) -> str | None:
    for name, value in scope.get("headers", []):
        if name == REQUEST_ID_HEADER.encode():
            candidate = value.decode("latin-1")
            return candidate if _VALID_REQUEST_ID.match(candidate) else None
    return None


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _incoming_request_id(scope) or new_request_id()
        scope.setdefault("state", {})["request_id"] = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        started = time.perf_counter()
        status_code = 500
        response_started = False

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]
                headers = list(message.get("headers", []))
                # Error responses already carry it (problem_response sets it).
                if not any(name.lower() == REQUEST_ID_HEADER.encode() for name, _ in headers):
                    headers.append((REQUEST_ID_HEADER.encode(), request_id.encode()))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception:
            log.exception("unhandled_exception")
            if response_started:
                # Headers are already on the wire; nothing sensible left to send.
                raise
            status_code = 500
            response = problem_response(
                status=500,
                code="internal_error",
                title="Internal error",
                detail="An unexpected error occurred. Quote the request id when reporting it.",
                request_id=request_id,
            )
            await response(scope, receive, send)
        finally:
            route = scope.get("route")
            log.info(
                "http_request",
                method=scope.get("method"),
                # The route template keeps ids out of the log and groups requests sensibly.
                route=getattr(route, "path", None),
                path=scope.get("path") if route is None else None,
                status=status_code,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
