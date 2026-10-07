"""Financial investigations: the full workflow from data to a verified final assessment.

Not a chatbot: an investigation has a fixed workflow (deterministic analytics → passport →
early warnings → stress tests → evidence → specialist agents → disagreement detection →
red-team challenge → senior synthesis → final assessment) and returns one structured record.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Body, Path, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from finpulse.agents.llm import LLMClient
from finpulse.api.deps import (
    Analyst,
    AuditSinkDep,
    DataSourceDep,
    LLMDep,
    OrgDep,
    PrincipalDep,
    SettingsDep,
    StoreDep,
    TrackerDep,
    Viewer,
)
from finpulse.api.routers.entities import EntityId
from finpulse.config import Settings
from finpulse.core.errors import ForbiddenError, NotFoundError
from finpulse.core.security import Principal
from finpulse.demo import DemoScriptLLM
from finpulse.investigation.audit import AuditSink, AuditTrail, InvestigationAuditor, verify_chain
from finpulse.investigation.orchestrator import InvestigationOrchestrator
from finpulse.investigation.schemas import (
    Investigation,
    InvestigationEvent,
    InvestigationProgress,
    InvestigationSummary,
)
from finpulse.services.entities import load_entity, resolve_as_of

router = APIRouter(prefix="/api/v1", dependencies=[Viewer], tags=["investigations"])
InvestigationId = Annotated[uuid.UUID, Path(description="Investigation id")]


class InvestigateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of: date | None = Field(default=None, description="Defaults to the end of the data")
    mode: Literal["live", "demo"] = Field(
        default="live",
        description="demo: answer with the scripted demo agents (Sharma Electricals only; see "
        "docs/DEMO.md) instead of the language model. The record is marked ai_mode=demo_script.",
    )


def choose_llm(llm: LLMClient, settings: Settings, request: InvestigateRequest | None) -> LLMClient:
    if request is None or request.mode == "live":
        return llm
    if not settings.demo_allowed:
        raise ForbiddenError("The scripted demo is disabled here.", code="demo_disabled")
    return DemoScriptLLM(settings.demo_script_pace)


async def open_audit(
    sink: AuditSink,
    principal: Principal,
    http: Request,
    llm: LLMClient,
    entity_id: uuid.UUID,
    as_of: date,
) -> InvestigationAuditor:
    """Write the first audit entry before anything runs; refuse to run unaudited (503)."""
    auditor = InvestigationAuditor(
        sink=sink,
        org_id=principal.org_id,
        investigation_id=uuid.uuid4(),
        actor=principal.name,
        request_id=getattr(http.state, "request_id", None),
    )
    await auditor.requested(entity_id, as_of, getattr(llm, "ai_mode", "live"), llm.model)
    return auditor


@router.post(
    "/entities/{entity_id}/investigate",
    dependencies=[Analyst],
    response_model=Investigation,
    summary="Run a complete financial investigation and return its structured record",
)
async def investigate(
    entity_id: EntityId,
    source: DataSourceDep,
    org_id: OrgDep,
    llm: LLMDep,
    store: StoreDep,
    tracker: TrackerDep,
    settings: SettingsDep,
    sink: AuditSinkDep,
    principal: PrincipalDep,
    http: Request,
    request: Annotated[InvestigateRequest | None, Body()] = None,
) -> Investigation:
    chosen = choose_llm(llm, settings, request)
    data = await load_entity(source, org_id, entity_id)
    as_of = resolve_as_of(data, request.as_of if request else None)
    tracker.acquire(org_id)
    try:
        auditor = await open_audit(sink, principal, http, chosen, entity_id, as_of)
        try:
            investigation = await InvestigationOrchestrator(auditor.wrap(chosen)).investigate(
                data, as_of, investigation_id=auditor.investigation_id
            )
        except BaseException as exc:
            await auditor.failed(exc)
            raise
        store.save(investigation, org_id)
        await auditor.completed(investigation)
        return investigation
    finally:
        tracker.release(org_id)


@router.post(
    "/entities/{entity_id}/investigations",
    dependencies=[Analyst],
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
    settings: SettingsDep,
    sink: AuditSinkDep,
    principal: PrincipalDep,
    http: Request,
    request: Annotated[InvestigateRequest | None, Body()] = None,
) -> InvestigationProgress:
    chosen = choose_llm(llm, settings, request)
    data = await load_entity(source, org_id, entity_id)
    as_of = resolve_as_of(data, request.as_of if request else None)
    tracker.acquire(org_id)
    try:
        auditor = await open_audit(sink, principal, http, chosen, entity_id, as_of)
        return tracker.start(chosen, data, as_of, store, auditor)
    except BaseException:
        tracker.release(org_id)  # the run never started, so it will not release the slot
        raise


@router.get(
    "/investigations/{investigation_id}/progress",
    response_model=InvestigationProgress,
    summary="Live progress of a background investigation (stages, agents, events)",
)
async def progress(
    investigation_id: InvestigationId, tracker: TrackerDep, org_id: OrgDep
) -> InvestigationProgress:
    found = tracker.get(investigation_id, org_id)
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
    org_id: OrgDep,
    entity_id: Annotated[uuid.UUID | None, Query(description="Only this entity's")] = None,
) -> list[InvestigationSummary]:
    return [s for s in store.summaries(org_id) if entity_id is None or s.entity_id == entity_id]


def _get(store: StoreDep, investigation_id: uuid.UUID, org_id: uuid.UUID) -> Investigation:
    found = store.get(investigation_id, org_id)
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
async def get_investigation(
    investigation_id: InvestigationId, store: StoreDep, org_id: OrgDep
) -> Investigation:
    return _get(store, investigation_id, org_id)


@router.get(
    "/investigations/{investigation_id}/events",
    response_model=list[InvestigationEvent],
    summary="The investigation's timestamped event log",
)
async def get_events(
    investigation_id: InvestigationId, store: StoreDep, org_id: OrgDep
) -> list[InvestigationEvent]:
    return _get(store, investigation_id, org_id).events


@router.get(
    "/investigations/{investigation_id}/audit",
    response_model=AuditTrail,
    summary="The investigation's append-only, hash-chained audit trail, and whether it verifies",
)
async def get_audit(
    investigation_id: InvestigationId, sink: AuditSinkDep, org_id: OrgDep
) -> AuditTrail:
    entries = await sink.read(org_id, investigation_id)
    if not entries:
        raise NotFoundError(
            f"No audit trail for investigation {investigation_id}.",
            code="investigation_not_found",
        )
    broken = verify_chain(entries)
    return AuditTrail(
        investigation_id=investigation_id,
        entries=entries,
        chain_valid=broken is None,
        broken_at_seq=broken,
    )
