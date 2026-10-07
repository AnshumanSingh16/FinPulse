from __future__ import annotations

import os
from collections.abc import AsyncIterator, Callable

import httpx
import pytest
from fastapi import FastAPI

from finpulse.config import Settings
from finpulse.main import create_app

# A port nothing listens on: tests that don't need a database must not depend on one.
UNREACHABLE_DATABASE_URL = "postgresql://finpulse:finpulse@127.0.0.1:1/finpulse"


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "FINPULSE_ENV": "test",
        "LOG_FORMAT": "json",
        "LOG_LEVEL": "INFO",
        "DATABASE_URL": UNREACHABLE_DATABASE_URL,
        "DATABASE_CONNECT_TIMEOUT_S": 1,
        "CORS_ALLOWED_ORIGINS": "http://localhost:3000",
        "AUDIT_BACKEND": "memory",
    }
    values.update(overrides)
    # _env_file=None: tests never read the developer's .env
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def app_factory() -> Callable[..., FastAPI]:
    return lambda **overrides: create_app(make_settings(**overrides))


async def client_for(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client


@pytest.fixture
async def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async for c in client_for(app):
        yield c


@pytest.fixture
async def db_client() -> AsyncIterator[httpx.AsyncClient]:
    """Client wired to a real PostgreSQL from TEST_DATABASE_URL; skips when not set."""
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    async for c in client_for(create_app(make_settings(DATABASE_URL=url))):
        yield c
