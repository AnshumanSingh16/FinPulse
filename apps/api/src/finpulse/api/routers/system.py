"""Operational endpoints. Unversioned and unauthenticated so probes and the web shell can
reach them before any user is signed in. They expose no tenant data."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from finpulse import __version__
from finpulse.api.deps import EngineDep, SettingsDep
from finpulse.api.schemas.system import DependencyCheck, HealthResponse, ReadinessResponse
from finpulse.observability.logging import get_logger
from finpulse.persistence.db import ping

SERVICE_NAME = "finpulse-api"

router = APIRouter(tags=["system"])
log = get_logger(__name__)


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
async def health(settings: SettingsDep) -> HealthResponse:
    return HealthResponse(
        status="ok",
        service=SERVICE_NAME,
        version=__version__,
        environment=settings.env,
        timestamp=datetime.now(UTC),
    )


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness probe",
    responses={503: {"model": ReadinessResponse, "description": "A dependency is unavailable"}},
)
async def ready(settings: SettingsDep, engine: EngineDep) -> JSONResponse:
    try:
        latency = await ping(engine, timeout_s=settings.database_connect_timeout_s + 1)
        database = DependencyCheck(name="database", status="ok", latency_ms=round(latency, 2))
    except Exception as exc:  # any failure here means "not ready", never a 500
        # Exception text from drivers can include the host; never the password, since the URL
        # is not part of connection errors, but keep the detail to the exception type anyway.
        log.warning("readiness_check_failed", check="database", error=type(exc).__name__)
        database = DependencyCheck(
            name="database", status="failed", detail=f"{type(exc).__name__}: database unreachable"
        )

    checks = [database]
    is_ready = all(check.status == "ok" for check in checks)
    body = ReadinessResponse(status="ready" if is_ready else "not_ready", checks=checks)
    return JSONResponse(status_code=200 if is_ready else 503, content=body.model_dump(mode="json"))
