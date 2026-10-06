"""HTTP API for the Financial Passport."""

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest

from finpulse.api.deps import get_financial_data_source
from finpulse.main import create_app
from finpulse.scoring import load_model
from tests.conftest import client_for, make_settings
from tests.test_entities_api import ANANYA, SHARMA, InMemorySource

PROBLEM = "application/problem+json"


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(make_settings())
    source = InMemorySource(SHARMA, ANANYA)
    app.dependency_overrides[get_financial_data_source] = lambda: source
    async for c in client_for(app):
        yield c


def url(suffix: str = "", entity: uuid.UUID = SHARMA.entity_id) -> str:
    return f"/api/v1/entities/{entity}/passport{suffix}"


async def test_passport(client: httpx.AsyncClient) -> None:
    response = await client.get(url())

    assert response.status_code == 200
    body = response.json()
    assert body["as_of"] == "2026-09-30"
    assert "not a credit score" in body["disclaimer"].lower()
    health = body["financial_health"]
    assert set(health) == {"score", "band", "confidence", "provisional"}
    assert [d["name"] for d in body["dimensions"]] == [
        "Cash-Flow Stability",
        "Repayment Capacity",
        "Revenue Stability",
        "Financial Resilience",
        "Debt Health",
        "Transaction Consistency",
    ]
    factor = body["dimensions"][0]["factors"][0]
    assert set(factor) >= {
        "metric_code",
        "metric_value",
        "points",
        "contribution_to_overall",
        "explanation",
    }
    assert body["change_from_previous_month"]["from_as_of"] == "2026-08-31"
    assert body["concerns"] and body["strengths"]


async def test_passport_as_of(client: httpx.AsyncClient) -> None:
    earlier = (await client.get(url(), params={"as_of": "2025-10-31"})).json()
    latest = (await client.get(url())).json()

    assert earlier["as_of"] == "2025-10-31"
    assert float(earlier["financial_health"]["score"]) > float(latest["financial_health"]["score"])


async def test_history(client: httpx.AsyncClient) -> None:
    response = await client.get(url("/history"))

    assert response.status_code == 200
    body = response.json()
    assert len(body["points"]) == 12  # default
    assert body["points"][-1]["as_of"] == "2026-09-30"
    assert len(body["changes"]) == 11
    assert set(body["points"][0]["dimensions"]) == set(load_model().dimensions)
    assert "not a credit score" in body["disclaimer"].lower()


async def test_history_months_parameter(client: httpx.AsyncClient) -> None:
    body = (await client.get(url("/history"), params={"months": 24})).json()

    assert len(body["points"]) == 18  # the whole history is 18 months


@pytest.mark.parametrize("months", [0, 25, "many"])
async def test_history_months_is_validated(client: httpx.AsyncClient, months: object) -> None:
    response = await client.get(url("/history"), params={"months": months})

    assert response.status_code == 422
    assert response.json()["errors"][0]["loc"] == ["query", "months"]


@pytest.mark.parametrize("suffix", ["", "/history"])
async def test_unknown_entity_is_404(client: httpx.AsyncClient, suffix: str) -> None:
    response = await client.get(url(suffix, uuid.uuid4()))

    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM
    assert response.json()["code"] == "entity_not_found"


async def test_before_the_history_is_422(client: httpx.AsyncClient) -> None:
    response = await client.get(url(), params={"as_of": "2020-01-01"})

    assert response.status_code == 422
    assert response.json()["code"] == "insufficient_history"


async def test_passport_model_is_published(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/v1/meta/passport-model")).json()

    assert body["model"]["version"] == 1
    assert set(body["dimensions"]) == set(load_model().dimensions)
    assert body["dimensions"]["debt_health"]["factors"][0]["breakpoints"]
