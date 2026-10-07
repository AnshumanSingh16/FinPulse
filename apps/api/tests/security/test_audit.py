"""The AI investigation audit trail (SECURITY.md §9)."""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from finpulse.api.deps import get_audit_sink
from finpulse.investigation.audit import (
    NO_DECISION,
    AuditRecord,
    InvestigationAuditor,
    MemoryAuditSink,
    verify_chain,
)
from finpulse.persistence.db import create_engine
from finpulse.persistence.repositories.ai_audit import PostgresAuditSink
from tests.agents.fakes import FakeLLM, pack_for
from tests.conftest import make_settings
from tests.security.helpers import DEMO_ORG_ID, OrgSource, auth, keyed_client
from tests.test_entities_api import MEHRA

API_DIR = Path(__file__).resolve().parents[2]
SOURCE = OrgSource({DEMO_ORG_ID: [MEHRA]})
URL = f"/api/v1/entities/{MEHRA.entity_id}/investigate"


@pytest.fixture
async def run() -> AsyncIterator[tuple[httpx.AsyncClient, FakeLLM, dict[str, Any]]]:
    llm = FakeLLM(pack_for("mehra_lighting"))
    async for c, _ in keyed_client(llm, SOURCE):
        body = (await c.post(URL, headers=auth("analyst"))).json()
        yield c, llm, body


async def trail(c: httpx.AsyncClient, inv: str) -> dict[str, Any]:
    response = await c.get(f"/api/v1/investigations/{inv}/audit", headers=auth("viewer"))
    assert response.status_code == 200
    return response.json()  # type: ignore[no-any-return]


async def test_every_investigation_leaves_a_valid_chain(run: Any) -> None:
    c, llm, body = run

    audit = await trail(c, body["investigation_id"])

    assert audit["chain_valid"] is True and audit["broken_at_seq"] is None
    events = [e["event"] for e in audit["entries"]]
    assert events[0] == "investigation_requested"
    assert events[-1] == "investigation_completed"
    assert events.count("llm_call") == len(llm.requests)
    assert events.count("agent_result") == 7
    assert [e["seq"] for e in audit["entries"]] == list(range(1, len(events) + 1))
    first = audit["entries"][0]
    assert first["actor"] == "a" and first["request_id"].startswith("req_")
    assert first["payload"]["entity_id"] == str(MEHRA.entity_id)


async def test_the_trail_records_hashes_not_prompts(run: Any) -> None:
    c, llm, body = run

    audit = await trail(c, body["investigation_id"])

    call = next(e for e in audit["entries"] if e["event"] == "llm_call")
    assert len(call["payload"]["request_sha256"]) == 64
    assert len(call["payload"]["response_sha256"]) == 64
    flat = str(audit)
    assert llm.requests[0].system[:80] not in flat
    done = audit["entries"][-1]["payload"]
    assert done["decision"] == NO_DECISION
    assert done["risk_level_deterministic"] == body["final_assessment"]["risk_level"]
    assert len(done["record_sha256"]) == 64


async def test_the_audit_endpoint_needs_a_key(run: Any) -> None:
    c, _, body = run

    response = await c.get(f"/api/v1/investigations/{body['investigation_id']}/audit")

    assert response.status_code == 401


def records(n: int = 4) -> list[AuditRecord]:
    sink = MemoryAuditSink()
    auditor = InvestigationAuditor(sink, DEMO_ORG_ID, uuid.uuid4(), "a", None)
    for i in range(n):
        auditor._add("llm_call", {"call": i})
    return list(auditor.pending)


def test_a_changed_entry_breaks_the_chain() -> None:
    chain = records()
    assert verify_chain(chain) is None

    chain[1] = chain[1].model_copy(update={"payload": {"call": 99}})

    assert verify_chain(chain) == 2


def test_a_deleted_entry_breaks_the_chain() -> None:
    chain = records()

    assert verify_chain([chain[0], chain[2], chain[3]]) == 3


def test_a_rehashed_forgery_still_breaks_the_chain() -> None:
    chain = records()
    forged = chain[1].model_copy(update={"payload": {"call": 99}})
    from finpulse.investigation.audit import entry_hash

    chain[1] = forged.model_copy(update={"hash": entry_hash(forged)})

    assert verify_chain(chain) == 3  # the next entry no longer points at it


class BrokenSink(MemoryAuditSink):
    async def append(self, records: list[AuditRecord]) -> None:
        raise OSError("disk full")


async def test_no_investigation_runs_if_the_audit_trail_cannot_be_written() -> None:
    llm = FakeLLM(pack_for("mehra_lighting"))
    async for c, app in keyed_client(llm, SOURCE):
        app.dependency_overrides[get_audit_sink] = BrokenSink
        for path in (URL, f"/api/v1/entities/{MEHRA.entity_id}/investigations"):
            response = await c.post(path, headers=auth("analyst"))
            assert response.status_code == 503
            assert response.json()["code"] == "audit_unavailable"
        assert llm.requests == []
        # the slot was released: a working sink can run immediately
        app.dependency_overrides.pop(get_audit_sink)
        assert (await c.post(URL, headers=auth("analyst"))).status_code == 200


async def test_a_failed_investigation_is_audited() -> None:
    from tests.test_agents_api import DownLLM

    async for c, app in keyed_client(DownLLM(), SOURCE):
        response = await c.post(URL, headers=auth("analyst"))
        assert response.status_code == 503
        sink = app.state.audit_sink
        [rec] = [r for r in sink.records if r.event == "investigation_failed"]
        assert rec.payload["error"] == "llm_unavailable"
        chain = await sink.read(DEMO_ORG_ID, rec.investigation_id)
        assert verify_chain(chain) is None


# --- PostgreSQL ---------------------------------------------------------------------------------


@pytest.mark.db
def test_postgres_trail_is_append_only() -> None:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    settings = make_settings(DATABASE_URL=url)
    config = Config(str(API_DIR / "alembic.ini"))
    config.attributes["configure_logger"] = False
    config.attributes["database_url"] = settings.database_url
    command.upgrade(config, "head")
    chain = records(3)

    async def go() -> tuple[list[AuditRecord], list[str]]:
        engine = create_engine(settings)
        refused = []
        try:
            sink = PostgresAuditSink(engine)
            await sink.append(chain)
            for sql in (
                "UPDATE ai_audit_events SET payload = '{}' WHERE investigation_id = :i",
                "DELETE FROM ai_audit_events WHERE investigation_id = :i",
            ):
                try:
                    async with engine.begin() as conn:
                        await conn.execute(text(sql), {"i": chain[0].investigation_id})
                except Exception as exc:
                    refused.append(str(exc))
            return await sink.read(DEMO_ORG_ID, chain[0].investigation_id), refused
        finally:
            await engine.dispose()

    stored, refused = asyncio.run(go())

    assert len(refused) == 2 and all("append-only" in r for r in refused)
    assert [r.hash for r in stored] == [r.hash for r in chain]
    assert verify_chain(stored) is None
