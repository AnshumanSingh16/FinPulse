"""Application factory.

Run with ``uvicorn --factory finpulse.main:create_app`` (or ``python -m finpulse``). Tests build
their own app with ``create_app(settings)`` so nothing global leaks between them.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from finpulse import __version__
from finpulse.api.errors import register_exception_handlers
from finpulse.api.middleware import REQUEST_ID_HEADER, RequestContextMiddleware
from finpulse.api.routers import (
    agents,
    demo,
    entities,
    investigations,
    passport,
    stress,
    system,
    warnings,
)
from finpulse.api.schemas.errors import ProblemDetails
from finpulse.config import Settings, get_settings
from finpulse.core.security import ApiKey, parse_api_keys
from finpulse.observability.logging import configure_logging, get_logger
from finpulse.persistence.db import create_engine, create_session_factory


def validate_security(settings: Settings) -> list[ApiKey]:
    """Refuse to start with an unsafe configuration (SECURITY.md)."""
    keys = parse_api_keys(settings.api_keys.get_secret_value() if settings.api_keys else None)
    if settings.env in ("staging", "production"):
        if not keys:
            raise RuntimeError(f"API_KEYS must be set when FINPULSE_ENV={settings.env}.")
        if "*" in settings.cors_allowed_origins:
            raise RuntimeError("CORS_ALLOWED_ORIGINS must list origins explicitly, not '*'.")
        if settings.audit_backend != "postgres":
            raise RuntimeError("AUDIT_BACKEND must be postgres outside development and test.")
    return keys


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)
    log = get_logger("finpulse.app")
    api_keys = validate_security(settings)
    if not api_keys:
        log.warning(
            "authentication_disabled",
            detail="No API_KEYS configured: every request acts as a local administrator. "
            "Allowed only in development and test.",
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings)
        app.state.db_engine = engine
        app.state.db_sessions = create_session_factory(engine)
        log.info("startup", environment=settings.env, version=__version__)
        try:
            yield
        finally:
            await engine.dispose()
            log.info("shutdown")

    app = FastAPI(
        title="FinPulse API",
        version=__version__,
        description="Financial intelligence for thin-file individuals and small businesses.",
        lifespan=lifespan,
        # Interactive docs are a development convenience, not a production surface.
        docs_url="/docs" if settings.env != "production" else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.env != "production" else None,
        responses={
            "default": {"model": ProblemDetails, "description": "Error (application/problem+json)"}
        },
    )
    app.state.settings = settings
    app.state.api_keys = api_keys

    register_exception_handlers(app)

    # Added first so it sits inside CORS: error responses produced here still get CORS headers.
    app.add_middleware(RequestContextMiddleware, max_request_bytes=settings.max_request_bytes)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
        expose_headers=[REQUEST_ID_HEADER],
    )

    app.include_router(system.router)
    app.include_router(entities.router)  # /api/v1/...
    app.include_router(passport.router)
    app.include_router(stress.router)
    app.include_router(warnings.router)
    app.include_router(agents.router)
    app.include_router(investigations.router)
    app.include_router(demo.router)

    return app
