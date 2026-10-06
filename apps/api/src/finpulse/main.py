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
from finpulse.api.routers import entities, passport, stress, system
from finpulse.api.schemas.errors import ProblemDetails
from finpulse.config import Settings, get_settings
from finpulse.observability.logging import configure_logging, get_logger
from finpulse.persistence.db import create_engine, create_session_factory


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)
    log = get_logger("finpulse.app")

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

    register_exception_handlers(app)

    # Added first so it sits inside CORS: error responses produced here still get CORS headers.
    app.add_middleware(RequestContextMiddleware)
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

    return app
