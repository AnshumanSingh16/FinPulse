"""FastAPI dependencies shared by routers."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from finpulse.agents.llm import AnthropicLLM, LLMClient
from finpulse.config import Settings
from finpulse.investigation.progress import ProgressTracker
from finpulse.investigation.store import InvestigationStore
from finpulse.persistence.db import session_scope
from finpulse.persistence.repositories.financial_data import (
    FinancialDataSource,
    PostgresFinancialDataSource,
)
from finpulse.synthetic.ids import DEMO_ORG_ID


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_engine(request: Request) -> AsyncEngine:
    engine: AsyncEngine = request.app.state.db_engine
    return engine


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async for session in session_scope(request.app.state.db_sessions):
        yield session


def get_current_org_id() -> uuid.UUID:
    """The caller's organisation. Until authentication lands (DEVELOPMENT_PLAN Phase 0, remaining
    work) every request acts within the demo organisation that `finpulse db seed` creates."""
    return DEMO_ORG_ID


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
        tracker = ProgressTracker(request.app.state.settings.investigations_keep)
        request.app.state.progress = tracker
    return tracker


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
EngineDep = Annotated[AsyncEngine, Depends(get_engine)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
OrgDep = Annotated[uuid.UUID, Depends(get_current_org_id)]
DataSourceDep = Annotated[FinancialDataSource, Depends(get_financial_data_source)]
LLMDep = Annotated[LLMClient, Depends(get_llm_client)]
StoreDep = Annotated[InvestigationStore, Depends(get_investigation_store)]
TrackerDep = Annotated[ProgressTracker, Depends(get_progress_tracker)]
