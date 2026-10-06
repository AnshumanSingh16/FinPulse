"""Load generated datasets into PostgreSQL.

Seeding is idempotent: subject ids are deterministic, so re-seeding a scenario deletes that
subject (cascading to all its rows) and inserts it again, inside one transaction. Running it twice
leaves exactly the same rows.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from finpulse.observability.logging import get_logger
from finpulse.persistence import models
from finpulse.persistence.base import Base
from finpulse.synthetic import SCENARIOS, generate
from finpulse.synthetic.export import Row, fingerprint, to_records
from finpulse.synthetic.ids import DEMO_ORG_ID
from finpulse.synthetic.model import Dataset

DEMO_ORG_NAME = "FinPulse Demo"
# Generator field names that differ from column names.
RENAMES = {
    "invoice_payments": {"document_id": "invoice_id"},
    "bill_payments": {"document_id": "bill_id"},
}

log = get_logger(__name__)


@dataclass(frozen=True)
class SeedResult:
    scenario_code: str
    subject_id: uuid.UUID
    fingerprint: str
    rows: dict[str, int]


async def ensure_demo_org(conn: AsyncConnection) -> uuid.UUID:
    exists = await conn.scalar(
        select(models.Organization.id).where(models.Organization.id == DEMO_ORG_ID)
    )
    if exists is None:
        await conn.execute(insert(models.Organization).values(id=DEMO_ORG_ID, name=DEMO_ORG_NAME))
    return DEMO_ORG_ID


def _prepare(table: str, rows: list[Row], org_id: uuid.UUID) -> list[Row]:
    rename = RENAMES.get(table, {})
    prepared = []
    for row in rows:
        out = {rename.get(k, k): v for k, v in row.items()}
        out["org_id"] = org_id
        if table == "subjects":
            out["data_origin"] = "synthetic"
        prepared.append(out)
    return prepared


async def load_dataset(conn: AsyncConnection, ds: Dataset, org_id: uuid.UUID) -> dict[str, int]:
    """Replace one subject's data. Call inside a transaction."""
    await conn.execute(delete(models.Subject).where(models.Subject.id == ds.subject.id))
    counts: dict[str, int] = {}
    for table, rows in to_records(ds).items():
        if rows:
            await conn.execute(insert(Base.metadata.tables[table]), _prepare(table, rows, org_id))
        counts[table] = len(rows)
    return counts


async def seed(engine: AsyncEngine, scenario_codes: list[str] | None = None) -> list[SeedResult]:
    codes = scenario_codes or list(SCENARIOS)
    results = []
    for code in codes:
        ds = generate(SCENARIOS[code])
        async with engine.begin() as conn:
            org_id = await ensure_demo_org(conn)
            counts = await load_dataset(conn, ds, org_id)
        result = SeedResult(code, ds.subject.id, fingerprint(ds), counts)
        log.info("seeded_scenario", scenario=code, transactions=counts["transactions"])
        results.append(result)
    return results


async def table_counts(engine: AsyncEngine) -> dict[str, int]:
    async with engine.connect() as conn:
        return {
            name: int(await conn.scalar(select(func.count()).select_from(table)) or 0)
            for name, table in Base.metadata.tables.items()
        }
