"""Request context: correlation id, access logging, security headers, a request-size limit and
the last-resort error handler.

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
# Every response: financial data must not be cached, sniffed into another type or framed.
SECURITY_HEADERS: tuple[tuple[bytes, bytes], ...] = (
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"cache-control", b"no-store"),
)


def new_request_id() -> str:
    return f"req_{uuid.uuid4().hex}"


def _incoming_request_id(scope: Scope) -> str | None:
    for name, value in scope.get("headers", []):
        if name == REQUEST_ID_HEADER.encode():
            candidate = value.decode("latin-1")
            return candidate if _VALID_REQUEST_ID.match(candidate) else None
    return None


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp, max_request_bytes: int = 1_000_000) -> None:
        self.app = app
        self.max_request_bytes = max_request_bytes

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
        received = 0
        too_large = False

        async def limited_receive() -> Message:
            # Past the limit, tell the app the client went away (it stops reading) and answer
            # 413 ourselves once it returns; whatever it tries to send is dropped.
            nonlocal received, too_large
            if too_large:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_request_bytes:
                    too_large = True
                    return {"type": "http.disconnect"}
            return message

        declared = next(
            (v for k, v in scope.get("headers", []) if k == b"content-length"), b""
        ).decode("latin-1")
        if declared.isdigit() and int(declared) > self.max_request_bytes:
            await self._too_large(scope, receive, send, request_id)
            return

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code, response_started
            if too_large and not response_started:
                return
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]
                headers = list(message.get("headers", []))
                # Error responses already carry it (problem_response sets it).
                if not any(name.lower() == REQUEST_ID_HEADER.encode() for name, _ in headers):
                    headers.append((REQUEST_ID_HEADER.encode(), request_id.encode()))
                present = {name.lower() for name, _ in headers}
                headers += [(k, v) for k, v in SECURITY_HEADERS if k not in present]
                message["headers"] = headers
            await send(message)

        try:
            try:
                await self.app(scope, limited_receive, send_with_request_id)
            except Exception:
                if not (too_large and not response_started):
                    raise
                # The app gave up reading the oversized body; the 413 below answers.
            if too_large and not response_started:
                status_code = 413
                too_large = False  # let the 413 itself through
                await self._too_large(scope, receive, send_with_request_id, request_id)
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

    async def _too_large(self, scope: Scope, receive: Receive, send: Send, request_id: str) -> None:
        response = problem_response(
            status=413,
            code="request_too_large",
            title="Request too large",
            detail=f"Request bodies are limited to {self.max_request_bytes} bytes.",
            request_id=request_id,
        )
        await response(scope, receive, send)
