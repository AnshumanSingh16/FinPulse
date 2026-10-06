"""HTTP API for stress tests."""

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest

from finpulse.api.deps import get_financial_data_source
from finpulse.main import create_app
from finpulse.stress import PRESETS, SHOCKS
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


def url(entity: uuid.UUID = SHARMA.entity_id) -> str:
    return f"/api/v1/entities/{entity}/stress-test"


async def test_preset(client: httpx.AsyncClient) -> None:
    response = await client.post(url(), json={"preset": "revenue_down_20"})

    assert response.status_code == 200
    body = response.json()
    assert body["scenario"]["name"] == "Revenue decreases by 20%"
    assert set(body) >= {
        "baseline",
        "stressed",
        "comparisons",
        "risk_change",
        "health_impact",
        "evidence",
        "disclaimer",
    }
    keys = {c["key"] for c in body["comparisons"]}
    assert keys >= {
        "revenue",
        "expenses",
        "net_cash_flow",
        "closing_balance",
        "liquidity_ratio",
        "cash_runway_months",
        "financial_health_score",
    }
    stressed = body["stressed"]
    assert set(stressed) >= {
        "revenue",
        "expenses",
        "net_cash_flow",
        "closing_balance",
        "liquidity_ratio",
        "cash_runway_months",
        "financial_health_score",
        "risk",
        "failure_point",
        "months",
    }
    assert stressed["risk"]["level"] in {"low", "elevated", "high", "critical"}


async def test_custom_compound_shocks(client: httpx.AsyncClient) -> None:
    response = await client.post(
        url(),
        json={
            "shocks": [
                {"type": "customer_payment_stop", "days": 45},
                {
                    "type": "new_debt",
                    "principal": "200000",
                    "annual_rate": "0.2",
                    "tenor_months": 12,
                },
            ],
            "horizon_months": 9,
            "as_of": "2026-06-30",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["as_of"] == "2026-06-30" and body["horizon_months"] == 9
    assert len(body["stressed"]["months"]) == 9
    shocks = body["scenario"]["shocks"]
    assert [s["type"] for s in shocks] == ["customer_payment_stop", "new_debt"]
    assert shocks[0]["parameters"]["customer_id"]  # default resolved and reported


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"preset": "revenue_down_20", "shocks": [{"type": "new_debt"}]},
        {"preset": "end_of_the_world"},
        {"shocks": []},
        {"shocks": [{"type": "revenue_decline", "decline_pct": "1.5"}]},
        {"shocks": [{"type": "revenue_decline"}]},
        {"shocks": [{"type": "alien_invasion"}]},
        {"shocks": [{"type": "new_debt", "colour": "red"}]},
        {"preset": "revenue_down_20", "horizon_months": 25},
    ],
)
async def test_invalid_requests_are_422(client: httpx.AsyncClient, body: dict) -> None:
    response = await client.post(url(), json=body)

    assert response.status_code == 422
    assert response.headers["content-type"] == PROBLEM
    assert response.json()["code"] == "validation_error"


async def test_not_applicable_scenario_is_422(client: httpx.AsyncClient) -> None:
    response = await client.post(
        url(ANANYA.entity_id), json={"preset": "major_supplier_cost_up_10"}
    )

    assert response.status_code == 422
    assert response.json()["code"] == "scenario_not_applicable"


async def test_unknown_customer_is_not_applicable(client: httpx.AsyncClient) -> None:
    response = await client.post(
        url(),
        json={
            "shocks": [
                {"type": "customer_payment_stop", "days": 30, "customer_id": str(uuid.uuid4())}
            ]
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "scenario_not_applicable"


async def test_unknown_entity_is_404(client: httpx.AsyncClient) -> None:
    response = await client.post(url(uuid.uuid4()), json={"preset": "new_debt"})

    assert response.status_code == 404
    assert response.json()["code"] == "entity_not_found"


async def test_catalogue(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/v1/meta/stress-scenarios")).json()

    assert {s["type"] for s in body["shock_types"]} == set(SHOCKS)
    assert {p["code"] for p in body["presets"]} == set(PRESETS)
    revenue = next(s for s in body["shock_types"] if s["type"] == "revenue_decline")
    assert "decline_pct" in revenue["parameters_schema"]["properties"]
