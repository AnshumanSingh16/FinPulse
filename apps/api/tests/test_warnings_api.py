"""HTTP API for early warnings and the risk summary."""

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest

from finpulse.api.deps import get_financial_data_source
from finpulse.early_warning import RULES
from finpulse.main import create_app
from tests.conftest import client_for, make_settings
from tests.test_entities_api import ANANYA, MEHRA, InMemorySource

PROBLEM = "application/problem+json"
FIELDS = {
    "id",
    "category",
    "severity",
    "title",
    "description",
    "evidence",
    "affected_metric",
    "current_value",
    "previous_value",
    "threshold",
    "detected_at",
}


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(make_settings())
    source = InMemorySource(MEHRA, ANANYA)
    app.dependency_overrides[get_financial_data_source] = lambda: source
    async for c in client_for(app):
        yield c


def url(what: str, entity: uuid.UUID = MEHRA.entity_id) -> str:
    return f"/api/v1/entities/{entity}/{what}"


async def test_warnings(client: httpx.AsyncClient) -> None:
    response = await client.get(url("warnings"))

    assert response.status_code == 200
    body = response.json()
    assert body["as_of"] == "2026-09-30"
    assert body["warnings"] and all(set(w) >= FIELDS for w in body["warnings"])
    first = body["warnings"][0]
    assert first["severity"] == "critical"
    assert first["detected_at"] == "2026-09-30T23:59:59+05:30"
    assert {"observed", "operator", "value", "tiers"} <= set(first["threshold"])
    assert len(body["rules"]) == len(RULES)
    assert "not a credit assessment" in body["disclaimer"]


async def test_filters(client: httpx.AsyncClient) -> None:
    everything = (await client.get(url("warnings"))).json()["warnings"]
    serious = (await client.get(url("warnings"), params={"min_severity": "high"})).json()
    debt = (await client.get(url("warnings"), params={"category": "debt"})).json()

    assert {w["severity"] for w in serious["warnings"]} <= {"high", "critical"}
    assert len(serious["warnings"]) < len(everything)
    assert debt["warnings"] and {w["category"] for w in debt["warnings"]} == {"debt"}


async def test_as_of_in_the_past(client: httpx.AsyncClient) -> None:
    body = (await client.get(url("warnings"), params={"as_of": "2025-12-31"})).json()

    assert body["as_of"] == "2025-12-31"
    assert all(w["detected_at"].startswith("2025-12-31") for w in body["warnings"])


async def test_risk_summary(client: httpx.AsyncClient) -> None:
    response = await client.get(url("risk-summary"))

    assert response.status_code == 200
    body = response.json()
    assert body["risk_level"] == "critical"
    assert 0 <= body["early_warning_index"] <= 100
    assert body["headline"].startswith("Critical early-warning risk")
    assert len(body["timeline"]) == 12 and body["timeline"][-1]["as_of"] == "2026-09-30"
    assert body["trend"]["compared_with"] == "2026-06-30"


@pytest.mark.parametrize(
    "params",
    [{"min_severity": "apocalyptic"}, {"category": "astrology"}, {"as_of": "yesterday"}],
)
async def test_bad_parameters_are_422(client: httpx.AsyncClient, params: dict[str, str]) -> None:
    response = await client.get(url("warnings"), params=params)

    assert response.status_code == 422
    assert response.headers["content-type"] == PROBLEM


async def test_date_before_the_data_is_422(client: httpx.AsyncClient) -> None:
    response = await client.get(url("risk-summary"), params={"as_of": "2020-01-01"})

    assert response.status_code == 422
    assert response.json()["code"] == "insufficient_history"


@pytest.mark.parametrize("what", ["warnings", "risk-summary"])
async def test_unknown_entity_is_404(client: httpx.AsyncClient, what: str) -> None:
    response = await client.get(url(what, uuid.uuid4()))

    assert response.status_code == 404
    assert response.json()["code"] == "entity_not_found"


async def test_rule_catalogue(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/v1/meta/early-warning-rules")).json()

    assert {r["code"] for r in body["rules"]} == set(RULES)
    revenue = next(r for r in body["rules"] if r["code"] == "revenue_decline")
    assert revenue["parameters"]["tiers"]["high"] == "-0.30"
    assert body["severity_points"]["critical"] == 40
