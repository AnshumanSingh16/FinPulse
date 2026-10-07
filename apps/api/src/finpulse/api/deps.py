"""FastAPI dependencies shared by routers."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

import structlog
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from finpulse.agents.llm import AnthropicLLM, LLMClient
from finpulse.config import Settings
from finpulse.core.errors import ForbiddenError, UnauthorizedError
from finpulse.core.security import LOCAL_DEVELOPER, ApiKey, Principal, Role, authenticate
from finpulse.investigation.audit import AuditSink, MemoryAuditSink
from finpulse.investigation.progress import ProgressTracker
from finpulse.investigation.store import InvestigationStore
from finpulse.persistence.db import session_scope
from finpulse.persistence.repositories.ai_audit import PostgresAuditSink
from finpulse.persistence.repositories.financial_data import (
    FinancialDataSource,
    PostgresFinancialDataSource,
)


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_engine(request: Request) -> AsyncEngine:
    engine: AsyncEngine = request.app.state.db_engine
    return engine


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async for session in session_scope(request.app.state.db_sessions):
        yield session


def _presented_key(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth[:7].lower() == "bearer ":
        return auth[7:].strip() or None
    return request.headers.get("x-api-key") or None


def get_principal(request: Request) -> Principal:
    """The authenticated caller (SECURITY.md). Without configured keys — development and test
    only, enforced at startup — every request acts as the local developer."""
    keys: list[ApiKey] = request.app.state.api_keys
    if not keys:
        principal = LOCAL_DEVELOPER
    else:
        presented = _presented_key(request)
        found = authenticate(presented, keys) if presented else None
        if found is None:
            raise UnauthorizedError(
                "Send a valid API key as 'Authorization: Bearer <key>'.",
                code="unauthorized" if presented is None else "invalid_api_key",
            )
        principal = found
    request.state.principal = principal
    structlog.contextvars.bind_contextvars(actor=principal.name)
    return principal


PrincipalDep = Annotated[Principal, Depends(get_principal)]


def require(role: Role):  # type: ignore[no-untyped-def]
    """Dependency: the caller must hold at least ``role``."""

    def check(principal: PrincipalDep) -> Principal:
        if not principal.can(role):
            raise ForbiddenError(
                f"This action needs the '{role}' role; the key '{principal.name}' has "
                f"'{principal.role}'.",
                code="insufficient_role",
            )
        return principal

    return check


def get_current_org_id(principal: PrincipalDep) -> uuid.UUID:
    """The caller's organisation: every data access is scoped to it."""
    return principal.org_id


def get_financial_data_source(request: Request) -> FinancialDataSource:
    return PostgresFinancialDataSource(request.app.state.db_engine)


def get_llm_client(request: Request) -> LLMClient:
    """One Claude client per app (it holds a connection pool), created on first use so the
    deterministic API never needs AI credentials."""
    llm: LLMClient | None = getattr(request.app.state, "llm", None)
    if llm is None:
        llm = AnthropicLLM(request.app.state.settings)
        request.app.state.llm = llm
    return llm


def get_investigation_store(request: Request) -> InvestigationStore:
    store: InvestigationStore | None = getattr(request.app.state, "investigations", None)
    if store is None:
        settings: Settings = request.app.state.settings
        store = InvestigationStore(settings.investigations_keep, settings.investigations_dir)
        request.app.state.investigations = store
    return store


def get_progress_tracker(request: Request) -> ProgressTracker:
    tracker: ProgressTracker | None = getattr(request.app.state, "progress", None)
    if tracker is None:
        settings: Settings = request.app.state.settings
        tracker = ProgressTracker(settings.investigations_keep, settings.investigations_max_running)
        request.app.state.progress = tracker
    return tracker


def get_audit_sink(request: Request) -> AuditSink:
    sink: AuditSink | None = getattr(request.app.state, "audit_sink", None)
    if sink is None:
        if request.app.state.settings.audit_backend == "memory":
            sink = MemoryAuditSink()
        else:
            sink = PostgresAuditSink(request.app.state.db_engine)
        request.app.state.audit_sink = sink
    return sink


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
EngineDep = Annotated[AsyncEngine, Depends(get_engine)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
OrgDep = Annotated[uuid.UUID, Depends(get_current_org_id)]
Viewer = Depends(require("viewer"))
Analyst = Depends(require("analyst"))
Admin = Depends(require("admin"))
DataSourceDep = Annotated[FinancialDataSource, Depends(get_financial_data_source)]
LLMDep = Annotated[LLMClient, Depends(get_llm_client)]
StoreDep = Annotated[InvestigationStore, Depends(get_investigation_store)]
TrackerDep = Annotated[ProgressTracker, Depends(get_progress_tracker)]
AuditSinkDep = Annotated[AuditSink, Depends(get_audit_sink)]
