"""Seeding into a real PostgreSQL (runs when TEST_DATABASE_URL is set; CI provides one)."""

import asyncio
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from finpulse.persistence.db import create_engine
from finpulse.persistence.seed import seed
from finpulse.synthetic import SCENARIOS, generate
from finpulse.synthetic.export import fingerprint
from finpulse.synthetic.summary import monthly_summary
from tests.conftest import make_settings

pytestmark = pytest.mark.db
API_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    config = Config(str(API_DIR / "alembic.ini"))
    config.attributes["configure_logger"] = False
    config.attributes["database_url"] = make_settings(DATABASE_URL=url).database_url
    command.upgrade(config, "head")
    return url


def run(url: str, work):  # type: ignore[no-untyped-def]
    async def go():  # type: ignore[no-untyped-def]
        engine = create_engine(make_settings(DATABASE_URL=url))
        try:
            return await work(engine)
        finally:
            await engine.dispose()

    return asyncio.run(go())


async def scalar(engine: AsyncEngine, sql: str, **params: object) -> object:
    async with engine.connect() as conn:
        return await conn.scalar(text(sql), params)


def test_seed_loads_every_row_and_is_idempotent(database_url: str) -> None:
    first = run(database_url, lambda e: seed(e))
    second = run(database_url, lambda e: seed(e))

    assert [r.rows for r in first] == [r.rows for r in second]
    for result in second:
        ds = generate(SCENARIOS[result.scenario_code])
        assert result.fingerprint == fingerprint(ds)
        stored = run(
            database_url,
            lambda e, r=result: scalar(
                e, "SELECT count(*) FROM transactions WHERE subject_id = :s", s=r.subject_id
            ),
        )
        assert stored == len(ds.transactions)


def test_sql_ledger_and_receivables_reconcile(database_url: str) -> None:
    run(database_url, lambda e: seed(e, ["sharma_electricals"]))
    ds = generate(SCENARIOS["sharma_electricals"])

    async def checks(engine: AsyncEngine) -> tuple[object, object, object]:
        broken_chain = await scalar(
            engine,
            """
            SELECT count(*) FROM (
              SELECT t.balance_after_minor,
                     a.opening_balance_minor
                       + sum(t.amount_minor) OVER (PARTITION BY t.account_id ORDER BY t.seq)
                       AS running
              FROM transactions t JOIN accounts a ON a.id = t.account_id
              WHERE t.subject_id = :s) x
            WHERE balance_after_minor <> running""",
            s=ds.subject.id,
        )
        receivable = await scalar(
            engine,
            """
            SELECT sum(i.total_minor) - coalesce(sum(p.paid), 0) FROM invoices i
            LEFT JOIN (SELECT invoice_id, sum(amount_minor) AS paid FROM invoice_payments
                       GROUP BY invoice_id) p ON p.invoice_id = i.id
            WHERE i.subject_id = :s""",
            s=ds.subject.id,
        )
        mismatched = await scalar(
            engine,
            """
            SELECT count(*) FROM invoice_payments p JOIN transactions t ON t.id = p.transaction_id
            WHERE p.subject_id = :s AND (t.amount_minor <> p.amount_minor
                                         OR t.posted_on <> p.paid_on)""",
            s=ds.subject.id,
        )
        return broken_chain, receivable, mismatched

    broken_chain, receivable, mismatched = run(database_url, checks)

    assert broken_chain == 0
    assert receivable == monthly_summary(ds)[-1].receivables_minor
    assert mismatched == 0
