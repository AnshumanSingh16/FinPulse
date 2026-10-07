"""PostgreSQL storage for the AI investigation audit trail (investigation/audit.py)."""

from __future__ import annotations

import uuid

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncEngine

from finpulse.investigation.audit import AuditRecord
from finpulse.persistence import models as m


class PostgresAuditSink:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def append(self, records: list[AuditRecord]) -> None:
        if not records:
            return
        async with self.engine.begin() as conn:
            await conn.execute(
                insert(m.AIAuditEvent), [r.model_dump(mode="python") for r in records]
            )

    async def read(self, org_id: uuid.UUID, investigation_id: uuid.UUID) -> list[AuditRecord]:
        async with self.engine.connect() as conn:
            rows = (
                await conn.execute(
                    select(m.AIAuditEvent)
                    .where(
                        m.AIAuditEvent.org_id == org_id,
                        m.AIAuditEvent.investigation_id == investigation_id,
                    )
                    .order_by(m.AIAuditEvent.seq)
                )
            ).mappings()
            return [AuditRecord.model_validate(dict(r)) for r in rows]

    async def investigations(self) -> list[tuple[uuid.UUID, uuid.UUID]]:
        """Every (org_id, investigation_id) with an audit trail, for `finpulse audit verify`."""
        async with self.engine.connect() as conn:
            rows = await conn.execute(
                select(m.AIAuditEvent.org_id, m.AIAuditEvent.investigation_id).distinct()
            )
            return [(r[0], r[1]) for r in rows]
