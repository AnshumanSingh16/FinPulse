"""HTTP API for investigations (scripted model: no network, no API key)."""

import json
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from finpulse.api.deps import get_financial_data_source, get_llm_client
from finpulse.main import create_app
from tests.agents.fakes import FakeLLM, pack_for
from tests.conftest import client_for, make_settings
from tests.test_agents_api import DownLLM
from tests.test_entities_api import ANANYA, SHARMA, InMemorySource

REQUIRED = {
    "investigation_id",
    "entity_id",
    "triggered_warnings",
    "financial_metrics_used",
    "agent_analyses",
    "red_team_findings",
    "final_assessment",
    "recommendations",
    "confidence",
    "started_at",
    "completed_at",
    "stages",
    "events",
    "disagreements",
    "evidence_references",
    "claim_audit",
}


async def make_client(llm: object, **settings: object) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(make_settings(**settings))
    source = InMemorySource(SHARMA, ANANYA)
    app.dependency_overrides[get_financial_data_source] = lambda: source
    app.dependency_overrides[get_llm_client] = lambda: llm
    async for c in client_for(app):
        yield c


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async for c in make_client(FakeLLM(pack_for())):
        yield c


def url(entity: uuid.UUID = SHARMA.entity_id) -> str:
    return f"/api/v1/entities/{entity}/investigate"


async def test_investigate_returns_the_complete_record(client: httpx.AsyncClient) -> None:
    response = await client.post(url())

    assert response.status_code == 200
    body = response.json()
    assert set(body) >= REQUIRED
    assert body["entity_id"] == str(SHARMA.entity_id)
    assert body["status"] == "completed"
    assert body["triggered_warnings"][0]["severity"] == "critical"
    assert body["final_assessment"]["risk_level"] == "critical"
    assert body["confidence"]["level"] in {"high", "medium", "low"}
    assert body["claim_audit"]["evidence_references_resolve"] is True
    assert [s["stage"] for s in body["stages"]][-1] == "final_assessment"


async def test_investigations_can_be_inspected_afterwards(client: httpx.AsyncClient) -> None:
    first = (await client.post(url())).json()
    second = (await client.post(url(ANANYA.entity_id), json={"as_of": "2026-06-30"})).json()

    listed = (await client.get("/api/v1/investigations")).json()
    assert [i["investigation_id"] for i in listed] == [
        second["investigation_id"],
        first["investigation_id"],
    ]
    assert listed[0]["entity_name"].startswith("Ananya Rao") and listed[0]["as_of"] == "2026-06-30"
    full = (await client.get(f"/api/v1/investigations/{first['investigation_id']}")).json()
    assert full == first
    events = (await client.get(f"/api/v1/investigations/{first['investigation_id']}/events")).json()
    assert events == first["events"] and events[-1]["event"] == "investigation_completed"


async def test_unknown_investigation_is_404(client: httpx.AsyncClient) -> None:
    response = await client.get(f"/api/v1/investigations/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json()["code"] == "investigation_not_found"


async def test_unknown_entity_is_404(client: httpx.AsyncClient) -> None:
    assert (await client.post(url(uuid.uuid4()))).status_code == 404


async def test_bad_body_is_422(client: httpx.AsyncClient) -> None:
    response = await client.post(url(), json={"question": "Is this business ok?"})

    assert response.status_code == 422  # a workflow, not a chatbot: no free-text questions


async def test_without_a_model_investigate_is_503() -> None:
    async for c in make_client(DownLLM()):
        response = await c.post(url())
        assert response.status_code == 503 and response.json()["code"] == "llm_unavailable"
        assert (await c.get("/api/v1/investigations")).json() == []


async def test_investigations_are_written_to_disk_when_configured(tmp_path: Path) -> None:
    async for c in make_client(FakeLLM(pack_for()), INVESTIGATIONS_DIR=str(tmp_path)):
        body = (await c.post(url())).json()

    saved = json.loads((tmp_path / f"{body['investigation_id']}.json").read_text())
    assert saved["investigation_id"] == body["investigation_id"]


async def test_store_keeps_only_the_most_recent() -> None:
    async for c in make_client(FakeLLM(pack_for()), INVESTIGATIONS_KEEP=1):
        await c.post(url())
        latest = (await c.post(url())).json()
        listed = (await c.get("/api/v1/investigations")).json()

    assert [i["investigation_id"] for i in listed] == [latest["investigation_id"]]


async def test_saved_investigation_renders_for_the_demo(tmp_path: Path) -> None:
    from finpulse.cli import main

    async for c in make_client(FakeLLM(pack_for()), INVESTIGATIONS_DIR=str(tmp_path)):
        body = (await c.post(url())).json()
    path = tmp_path / f"{body['investigation_id']}.json"

    import contextlib
    import io

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        main(["investigate", "show", str(path), "--events"])
    text = buffer.getvalue()

    for heading in (
        "WORKFLOW",
        "TRIGGERED WARNINGS",
        "AGENT ANALYSES",
        "RED TEAM",
        "FINAL ASSESSMENT",
        "RECOMMENDATIONS",
        "CONFIDENCE",
        "AUDIT",
        "EVENTS",
    ):
        assert heading in text
    assert "investigation_completed" in text


async def wait_for(c: httpx.AsyncClient, investigation_id: str) -> dict:  # type: ignore[type-arg]
    import asyncio

    for _ in range(200):
        body = (await c.get(f"/api/v1/investigations/{investigation_id}/progress")).json()
        if body["status"] != "running":
            return body  # type: ignore[no-any-return]
        await asyncio.sleep(0.02)
    raise AssertionError("investigation did not finish")


async def test_background_investigation_reports_live_progress(client: httpx.AsyncClient) -> None:
    started = await client.post(f"/api/v1/entities/{SHARMA.entity_id}/investigations")

    assert started.status_code == 202
    body = started.json()
    assert body["status"] == "running"
    assert [a["agent"] for a in body["agents"]][-1] == "senior_synthesis"
    assert [s["state"] for s in body["timeline"]["steps"]] == ["pending"] * 8

    done = await wait_for(client, body["investigation_id"])

    assert done["status"] == "completed" and done["error"] is None
    assert all(a["state"] == "succeeded" and a["claims"] for a in done["agents"])
    assert [s["stage"] for s in done["stages"]][-1] == "final_assessment"
    assert {"agent_started", "agent_completed"} <= {e["event"] for e in done["events"]}
    assert all(s["state"] == "completed" for s in done["timeline"]["steps"])
    full = await client.get(f"/api/v1/investigations/{body['investigation_id']}")
    assert full.status_code == 200 and full.json()["status"] == "completed"
    # The live timeline and the stored one are the same.
    assert full.json()["timeline"] == done["timeline"]
    mine = (
        await client.get("/api/v1/investigations", params={"entity_id": str(SHARMA.entity_id)})
    ).json()
    others = (
        await client.get("/api/v1/investigations", params={"entity_id": str(ANANYA.entity_id)})
    ).json()
    assert [i["investigation_id"] for i in mine] == [body["investigation_id"]] and others == []


async def test_background_investigation_failure_is_reported() -> None:
    async for c in make_client(DownLLM()):
        body = (await c.post(f"/api/v1/entities/{SHARMA.entity_id}/investigations")).json()
        done = await wait_for(c, body["investigation_id"])

        assert done["status"] == "failed"
        assert done["error"]["code"] == "llm_unavailable"
        states = [s["state"] for s in done["timeline"]["steps"]]
        assert states == ["completed"] + ["failed"] * 4 + ["skipped"] * 3
        assert "ANTHROPIC_API_KEY" in done["error"]["message"]
        assert (
            await c.get(f"/api/v1/investigations/{body['investigation_id']}")
        ).status_code == 404


async def test_unknown_progress_is_404(client: httpx.AsyncClient) -> None:
    response = await client.get(f"/api/v1/investigations/{uuid.uuid4()}/progress")

    assert response.status_code == 404
