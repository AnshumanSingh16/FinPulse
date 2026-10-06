"""Database engine and session management.

The backend talks to PostgreSQL through SQLAlchemy's async engine with the psycopg 3 driver.
Only standard PostgreSQL is used, so the same code runs against a local container or a
Supabase project; Supabase is never required.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from finpulse.config import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    # Creating the engine does not open a connection; the API starts even if the database is
    # down, and /ready reports it.
    return create_async_engine(
        settings.database_url,
        pool_size=settings.database_pool_size,
        pool_pre_ping=True,
        connect_args={"connect_timeout": max(1, int(settings.database_connect_timeout_s))},
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def session_scope(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """One session per unit of work: commit on success, roll back on any error."""
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def ping(engine: AsyncEngine, timeout_s: float) -> float:
    """Round-trip ``SELECT 1``; returns latency in milliseconds or raises."""
    started = time.perf_counter()
    async with asyncio.timeout(timeout_s):
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    return (time.perf_counter() - started) * 1000
