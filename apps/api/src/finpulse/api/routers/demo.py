"""The deterministic demo (docs/DEMO.md): what it shows, and a reset to its exact starting state."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import BaseModel

from finpulse.api.deps import EngineDep, SettingsDep, StoreDep, TrackerDep
from finpulse.core.errors import ForbiddenError
from finpulse.demo.story import DemoInfo, demo_info
from finpulse.observability.logging import get_logger
from finpulse.persistence.seed import seed

router = APIRouter(prefix="/api/v1/demo", tags=["demo"])
log = get_logger("finpulse.demo")


class SeededEntity(BaseModel):
    scenario: str
    entity_id: uuid.UUID
    fingerprint: str


class DemoResetResult(BaseModel):
    reset_at: datetime
    seeded: list[SeededEntity]
    investigations_cleared: int
    runs_cleared: int


class DemoResetRequest(BaseModel):
    seed: bool = True


@router.get("", response_model=DemoInfo, summary="The demo walkthrough and its entity")
async def get_demo(settings: SettingsDep) -> DemoInfo:
    return demo_info(settings.demo_allowed)


@router.post(
    "/reset",
    response_model=DemoResetResult,
    summary="Restore the exact demo state: re-seed every synthetic entity, clear investigations",
)
async def reset_demo(
    settings: SettingsDep,
    engine: EngineDep,
    store: StoreDep,
    tracker: TrackerDep,
    request: DemoResetRequest | None = None,
) -> DemoResetResult:
    if not settings.demo_allowed:
        raise ForbiddenError("The demo reset is disabled here.", code="demo_disabled")
    seeded = await seed(engine) if request is None or request.seed else []
    result = DemoResetResult(
        reset_at=datetime.now(UTC),
        seeded=[
            SeededEntity(
                scenario=r.scenario_code, entity_id=r.subject_id, fingerprint=r.fingerprint
            )
            for r in seeded
        ],
        investigations_cleared=store.clear(),
        runs_cleared=tracker.clear(),
    )
    log.info(
        "demo_reset",
        seeded=len(result.seeded),
        investigations_cleared=result.investigations_cleared,
        runs_cleared=result.runs_cleared,
    )
    return result
