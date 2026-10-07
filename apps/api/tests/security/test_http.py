"""HTTP hardening: security headers on every response and a request-size limit."""

from __future__ import annotations

import httpx

from finpulse.main import create_app
from tests.conftest import client_for, make_settings


async def client(**settings: object):  # type: ignore[no-untyped-def]
    async for c in client_for(create_app(make_settings(**settings))):
        yield c


async def test_every_response_carries_security_headers() -> None:
    async for c in client():
        for response in (await c.get("/health"), await c.get("/api/v1/nowhere")):
            assert response.headers["x-content-type-options"] == "nosniff"
            assert response.headers["x-frame-options"] == "DENY"
            assert response.headers["referrer-policy"] == "no-referrer"
            assert response.headers["cache-control"] == "no-store"


async def test_oversized_bodies_are_refused_before_they_are_read() -> None:
    async for c in client(MAX_REQUEST_BYTES=2048):
        url = "/api/v1/entities/00000000-0000-0000-0000-000000000001/stress-test"
        response = await c.post(
            url, content=b"x" * 4096, headers={"content-type": "application/json"}
        )
        assert response.status_code == 413
        assert response.json()["code"] == "request_too_large"


async def test_a_streamed_oversized_body_is_refused() -> None:
    async def chunks():  # type: ignore[no-untyped-def]
        for _ in range(4):
            yield b"x" * 1024

    async for c in client(MAX_REQUEST_BYTES=2048):
        url = "/api/v1/entities/00000000-0000-0000-0000-000000000001/stress-test"
        response = await c.post(url, content=chunks(), headers={"content-type": "application/json"})
        assert response.status_code == 413


async def test_errors_never_leak_internals() -> None:
    async for c in client():
        response = await c.post(
            "/api/v1/entities/not-a-uuid/investigate", headers={"content-type": "application/json"}
        )
        assert response.headers["content-type"].startswith("application/problem+json")
        assert "Traceback" not in response.text and 'File "' not in response.text


__all__ = ["httpx"]
