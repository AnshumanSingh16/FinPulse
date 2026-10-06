"""FastAPI dependencies shared by routers."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from finpulse.config import Settings
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


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
EngineDep = Annotated[AsyncEngine, Depends(get_engine)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
OrgDep = Annotated[uuid.UUID, Depends(get_current_org_id)]
DataSourceDep = Annotated[FinancialDataSource, Depends(get_financial_data_source)]
