"""Financial investigations: the full workflow from data to a verified final assessment.

Not a chatbot: an investigation has a fixed workflow (deterministic analytics → passport →
early warnings → stress tests → evidence → specialist agents → disagreement detection →
red-team challenge → senior synthesis → final assessment) and returns one structured record.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Body, Path, Query
from pydantic import BaseModel, ConfigDict, Field

from finpulse.api.deps import DataSourceDep, LLMDep, OrgDep, StoreDep, TrackerDep
from finpulse.api.routers.entities import EntityId
from finpulse.core.errors import NotFoundError
from finpulse.investigation.orchestrator import InvestigationOrchestrator
from finpulse.investigation.schemas import (
    Investigation,
    InvestigationEvent,
    InvestigationProgress,
    InvestigationSummary,
)
from finpulse.services.entities import load_entity, resolve_as_of

router = APIRouter(prefix="/api/v1", tags=["investigations"])
InvestigationId = Annotated[uuid.UUID, Path(description="Investigation id")]


class InvestigateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of: date | None = Field(default=None, description="Defaults to the end of the data")


@router.post(
    "/entities/{entity_id}/investigate",
    response_model=Investigation,
    summary="Run a complete financial investigation and return its structured record",
)
async def investigate(
    entity_id: EntityId,
    source: DataSourceDep,
    org_id: OrgDep,
    llm: LLMDep,
    store: StoreDep,
    request: Annotated[InvestigateRequest | None, Body()] = None,
) -> Investigation:
    data = await load_entity(source, org_id, entity_id)
    as_of = resolve_as_of(data, request.as_of if request else None)
    investigation = await InvestigationOrchestrator(llm).investigate(data, as_of)
    store.save(investigation)
    return investigation


@router.post(
    "/entities/{entity_id}/investigations",
    response_model=InvestigationProgress,
    status_code=202,
    summary="Start an investigation in the background; follow it via /progress",
)
async def start_investigation(
    entity_id: EntityId,
    source: DataSourceDep,
    org_id: OrgDep,
    llm: LLMDep,
    store: StoreDep,
    tracker: TrackerDep,
    request: Annotated[InvestigateRequest | None, Body()] = None,
) -> InvestigationProgress:
    data = await load_entity(source, org_id, entity_id)
    as_of = resolve_as_of(data, request.as_of if request else None)
    return tracker.start(llm, data, as_of, store)


@router.get(
    "/investigations/{investigation_id}/progress",
    response_model=InvestigationProgress,
    summary="Live progress of a background investigation (stages, agents, events)",
)
async def progress(investigation_id: InvestigationId, tracker: TrackerDep) -> InvestigationProgress:
    found = tracker.get(investigation_id)
    if found is None:
        raise NotFoundError(
            f"No running or recent investigation {investigation_id}.",
            code="investigation_not_found",
        )
    return found


@router.get(
    "/investigations",
    response_model=list[InvestigationSummary],
    summary="Recent investigations, newest first",
)
async def list_investigations(
    store: StoreDep,
    entity_id: Annotated[uuid.UUID | None, Query(description="Only this entity's")] = None,
) -> list[InvestigationSummary]:
    return [s for s in store.summaries() if entity_id is None or s.entity_id == entity_id]


def _get(store: StoreDep, investigation_id: uuid.UUID) -> Investigation:
    found = store.get(investigation_id)
    if found is None:
        raise NotFoundError(
            f"No investigation {investigation_id} (only recent ones are kept).",
            code="investigation_not_found",
        )
    return found


@router.get(
    "/investigations/{investigation_id}",
    response_model=Investigation,
    summary="A complete investigation record",
)
async def get_investigation(investigation_id: InvestigationId, store: StoreDep) -> Investigation:
    return _get(store, investigation_id)


@router.get(
    "/investigations/{investigation_id}/events",
    response_model=list[InvestigationEvent],
    summary="The investigation's timestamped event log",
)
async def get_events(
    investigation_id: InvestigationId, store: StoreDep
) -> list[InvestigationEvent]:
    return _get(store, investigation_id).events
