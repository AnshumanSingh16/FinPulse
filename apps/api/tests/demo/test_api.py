"""The demo endpoints and demo-mode investigations over HTTP."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

from finpulse.api.deps import get_financial_data_source, get_llm_client
from finpulse.main import create_app
from finpulse.synthetic import PRIMARY_DEMO, SCENARIOS, generate
from tests.analytics.synthetic_adapter import to_financial_data
from tests.conftest import client_for, make_settings
from tests.test_entities_api import InMemorySource
from tests.test_investigations_api import wait_for

SHARMA = to_financial_data(generate(SCENARIOS[PRIMARY_DEMO]))


class NoLLM:
    model = "none"

    async def complete(self, request: object) -> object:
        raise AssertionError("demo mode must not call the configured model")


async def make(**settings: object) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(make_settings(DEMO_SCRIPT_PACE=0, **settings))
    source = InMemorySource(SHARMA)
    app.dependency_overrides[get_financial_data_source] = lambda: source
    app.dependency_overrides[get_llm_client] = lambda: NoLLM()
    async for c in client_for(app):
        yield c


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async for c in make():
        yield c


async def test_demo_info(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/v1/demo")).json()
    assert body["enabled"] is True
    assert body["entity_id"] == str(SHARMA.entity_id)
    assert body["as_of"] == "2026-09-30"
    assert body["stress_preset"] == "major_customer_stops_paying_60_days"
    assert [s["number"] for s in body["steps"]] == [1, 2, 3, 4, 5, 6]


async def test_demo_mode_investigation_is_marked_and_kept(client: httpx.AsyncClient) -> None:
    url = f"/api/v1/entities/{SHARMA.entity_id}/investigations"
    started = (await client.post(url, json={"mode": "demo"})).json()
    assert started["ai_mode"] == "demo_script"
    done = await wait_for(client, started["investigation_id"])
    assert done["status"] == "completed", done["error"]
    full = (await client.get(f"/api/v1/investigations/{started['investigation_id']}")).json()
    assert full["ai_mode"] == "demo_script"
    listed = (await client.get("/api/v1/investigations")).json()
    assert listed[0]["ai_mode"] == "demo_script"

    # The reset forgets it (seed=false: the test has no database).
    reset = (await client.post("/api/v1/demo/reset", json={"seed": False})).json()
    assert reset["investigations_cleared"] == 1 and reset["runs_cleared"] == 1
    assert (await client.get("/api/v1/investigations")).json() == []


async def test_demo_is_refused_in_production() -> None:
    async for c in make(FINPULSE_ENV="production"):
        url = f"/api/v1/entities/{SHARMA.entity_id}/investigations"
        refused = await c.post(url, json={"mode": "demo"})
        assert refused.status_code == 403 and refused.json()["code"] == "demo_disabled"
        reset = await c.post("/api/v1/demo/reset", json={"seed": False})
        assert reset.status_code == 403
        assert (await c.get("/api/v1/demo")).json()["enabled"] is False
