"""HTTP API for the agent layer (with a scripted model: no network, no API key)."""

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest

from finpulse.agents.catalogue import AGENTS
from finpulse.agents.llm import LLMRequest, LLMResponse
from finpulse.api.deps import get_financial_data_source, get_llm_client
from finpulse.core.errors import LLMUnavailableError
from finpulse.main import create_app
from tests.agents.fakes import FakeLLM, pack_for
from tests.conftest import client_for, make_settings
from tests.test_entities_api import ANANYA, SHARMA, InMemorySource

PROBLEM = "application/problem+json"


class DownLLM:
    model = "down"

    async def complete(self, request: LLMRequest) -> LLMResponse:
        raise LLMUnavailableError("The AI layer is not configured: set ANTHROPIC_API_KEY.")


async def client_with(llm: object) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(make_settings())
    source = InMemorySource(SHARMA, ANANYA)
    app.dependency_overrides[get_financial_data_source] = lambda: source
    app.dependency_overrides[get_llm_client] = lambda: llm
    async for c in client_for(app):
        yield c


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async for c in client_with(FakeLLM(pack_for())):
        yield c


def url(what: str, entity: uuid.UUID = SHARMA.entity_id) -> str:
    return f"/api/v1/entities/{entity}/{what}"


async def test_evidence_pack(client: httpx.AsyncClient) -> None:
    body = (await client.get(url("evidence-pack"))).json()

    assert body["sha256"] == pack_for().sha256
    assert {i["kind"] for i in body["items"]} == {
        "fact",
        "calculated_metric",
        "forecast",
        "assumption",
    }


async def test_intelligence_report(client: httpx.AsyncClient) -> None:
    response = await client.post(url("intelligence"))

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "complete"
    assert set(body["agents"]) == set(AGENTS)
    assert body["synthesis"]["headline"]
    claim = body["synthesis"]["calculated_metrics"][0]
    assert claim["statement_type"] == "CALCULATED_METRIC" and claim["evidence_ids"]
    assert body["agents"]["risk_investigation"]["verification"]["passed"] is True


async def test_one_agent(client: httpx.AsyncClient) -> None:
    body = (await client.post(url("agents/red_team"), json={"as_of": "2026-09-30"})).json()

    assert body["result"]["agent"] == "red_team" and body["result"]["status"] == "succeeded"
    assert set(body["dependencies"]) == {
        "financial_profile",
        "credit_intelligence",
        "early_warning_investigation",
        "risk_investigation",
        "stress_interpretation",
    }


async def test_unknown_agent_is_404(client: httpx.AsyncClient) -> None:
    response = await client.post(url("agents/oracle"))

    assert response.status_code == 404 and response.json()["code"] == "agent_not_found"


async def test_unknown_entity_is_404(client: httpx.AsyncClient) -> None:
    response = await client.post(url("intelligence", uuid.uuid4()))

    assert response.status_code == 404


async def test_bad_body_is_422(client: httpx.AsyncClient) -> None:
    response = await client.post(url("intelligence"), json={"as_of": "soon", "x": 1})

    assert response.status_code == 422 and response.headers["content-type"] == PROBLEM


async def test_without_a_model_the_agents_answer_503() -> None:
    async for c in client_with(DownLLM()):
        response = await c.post(url("intelligence"))
        assert response.status_code == 503
        assert response.json()["code"] == "llm_unavailable"
        assert "ANTHROPIC_API_KEY" in response.json()["detail"]
        # the deterministic API is unaffected
        assert (await c.get(url("evidence-pack"))).status_code == 200


async def test_agent_catalogue(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/v1/meta/agents")).json()

    assert [a["name"] for a in body] == list(AGENTS)
    senior = body[-1]
    assert senior["depends_on"][-1] == "red_team"
    assert "facts" in senior["output_schema"]["properties"]


async def test_real_adapter_without_credentials_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    """The production dependency, with no key and an unreachable endpoint: never a real call."""
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("ANTHROPIC_CONFIG_DIR", "/nonexistent")
    app = create_app(make_settings(LLM_MAX_RETRIES=0, LLM_TIMEOUT_S=2))
    source = InMemorySource(SHARMA)
    app.dependency_overrides[get_financial_data_source] = lambda: source
    async for c in client_for(app):
        response = await c.post(url("agents/financial_profile"))

        assert response.status_code == 503
        assert response.json()["code"] == "llm_unavailable"
