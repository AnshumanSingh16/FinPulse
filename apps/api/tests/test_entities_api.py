"""HTTP API for entities and financial metrics."""

import asyncio
import os
import uuid
from collections.abc import AsyncIterator
from datetime import date
from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.config import Config

from finpulse.analytics import CATALOGUE, compute_report, default_as_of
from finpulse.analytics.inputs import FinancialData
from finpulse.api.deps import get_current_org_id, get_financial_data_source
from finpulse.api.schemas.entities import EntitySummary
from finpulse.main import create_app
from finpulse.persistence.db import create_engine
from finpulse.persistence.seed import seed
from finpulse.synthetic import SCENARIOS, generate
from finpulse.synthetic.ids import DEMO_ORG_ID
from tests.analytics.synthetic_adapter import to_financial_data
from tests.conftest import client_for, make_settings

SHARMA = to_financial_data(generate(SCENARIOS["sharma_electricals"]))
ANANYA = to_financial_data(generate(SCENARIOS["ananya_rao_design"]))
# The sudden-collapse story (critical warnings, bounced debits): fixtures for tests that need them.
MEHRA = to_financial_data(generate(SCENARIOS["mehra_lighting"]))
PROBLEM = "application/problem+json"


class InMemorySource:
    def __init__(self, *entities: FinancialData) -> None:
        self.entities = {e.entity_id: e for e in entities}

    async def list_entities(self, org_id: uuid.UUID) -> list[EntitySummary]:
        assert org_id == DEMO_ORG_ID
        return [
            EntitySummary(
                id=e.entity_id,
                display_name=e.display_name,
                kind=e.kind,
                segment=e.segment,
                data_origin="synthetic",
            )
            for e in self.entities.values()
        ]

    async def load(self, org_id: uuid.UUID, entity_id: uuid.UUID) -> FinancialData | None:
        assert org_id == DEMO_ORG_ID
        return self.entities.get(entity_id)


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(make_settings())
    source = InMemorySource(SHARMA, ANANYA)
    app.dependency_overrides[get_financial_data_source] = lambda: source
    async for c in client_for(app):
        yield c


def url(entity: FinancialData, suffix: str = "") -> str:
    return f"/api/v1/entities/{entity.entity_id}/financial-metrics{suffix}"


async def test_lists_entities(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/entities")

    assert response.status_code == 200
    assert {e["display_name"] for e in response.json()} == {
        "Sharma Electricals",
        "Ananya Rao (UX design consultant)",
    }


async def test_financial_metrics_report(client: httpx.AsyncClient) -> None:
    response = await client.get(url(SHARMA))

    assert response.status_code == 200
    body = response.json()
    assert body["entity"]["display_name"] == "Sharma Electricals"
    assert body["as_of"] == "2026-09-30"  # defaults to the end of the data
    assert [m["code"] for m in body["metrics"]] == list(CATALOGUE)
    receivable_days = next(m for m in body["metrics"] if m["code"] == "receivables.days")
    assert set(receivable_days) >= {
        "code",
        "name",
        "value",
        "unit",
        "period",
        "availability",
        "confidence",
        "method",
        "components",
        "sources",
        "notes",
        "version",
    }
    assert receivable_days["unit"] == "days" and isinstance(receivable_days["value"], str)
    assert {s["code"] for s in body["series"]} >= {"revenue.monthly", "cash.balance"}


async def test_report_matches_the_engine_exactly(client: httpx.AsyncClient) -> None:
    body = (await client.get(url(SHARMA))).json()

    expected = compute_report(SHARMA, default_as_of(SHARMA)).model_dump(mode="json")  # type: ignore[arg-type]
    assert body == expected


async def test_as_of_moves_the_calculation_date(client: httpx.AsyncClient) -> None:
    body = (await client.get(url(SHARMA), params={"as_of": "2025-10-31"})).json()

    assert body["as_of"] == "2025-10-31"
    balance = next(m for m in body["metrics"] if m["code"] == "cash.balance")
    assert balance["period"]["end"] == "2025-10-31" and float(balance["value"]) > 0


async def test_single_metric(client: httpx.AsyncClient) -> None:
    response = await client.get(url(ANANYA, "/payables.days"))

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "payables.days"
    assert body["availability"] == "not_applicable" and body["value"] is None


async def test_unknown_entity_is_404(client: httpx.AsyncClient) -> None:
    response = await client.get(f"/api/v1/entities/{uuid.uuid4()}/financial-metrics")

    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM
    assert response.json()["code"] == "entity_not_found"


async def test_unknown_metric_is_404(client: httpx.AsyncClient) -> None:
    response = await client.get(url(SHARMA, "/revenue.everything"))

    assert response.status_code == 404
    assert response.json()["code"] == "metric_not_found"
    assert "receivables.days" in response.json()["extra"]["known"]


async def test_as_of_before_the_history_is_422(client: httpx.AsyncClient) -> None:
    response = await client.get(url(SHARMA), params={"as_of": "2020-01-01"})

    assert response.status_code == 422
    assert response.json()["code"] == "insufficient_history"


@pytest.mark.parametrize("bad", ["yesterday", "2026-13-01"])
async def test_malformed_as_of_is_a_validation_error(client: httpx.AsyncClient, bad: str) -> None:
    response = await client.get(url(SHARMA), params={"as_of": bad})

    assert response.status_code == 422
    assert response.json()["errors"][0]["loc"] == ["query", "as_of"]


async def test_malformed_entity_id_is_a_validation_error(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/entities/not-a-uuid/financial-metrics")

    assert response.status_code == 422


async def test_metric_catalogue(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/v1/meta/financial-metrics")).json()

    assert [d["code"] for d in body] == list(CATALOGUE)
    assert all(d["method"] and d["unit"] for d in body)


async def test_database_outage_is_a_503() -> None:
    # Default data source, and the test settings point at a port nothing listens on.
    async for client in client_for(create_app(make_settings())):
        response = await client.get("/api/v1/entities")

        assert response.status_code == 503
        assert response.headers["content-type"] == PROBLEM
        assert response.json()["code"] == "database_unavailable"
        assert response.headers["retry-after"] == "5"


def test_org_scope_defaults_to_the_demo_org() -> None:
    assert get_current_org_id() == DEMO_ORG_ID


@pytest.mark.db
async def test_metrics_from_postgres_equal_metrics_from_the_generator() -> None:
    url_ = os.environ.get("TEST_DATABASE_URL")
    if not url_:
        pytest.skip("TEST_DATABASE_URL not set")
    settings = make_settings(DATABASE_URL=url_)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.attributes.update(configure_logger=False, database_url=settings.database_url)
    await asyncio.to_thread(command.upgrade, config, "head")
    engine = create_engine(settings)
    try:
        await seed(engine, ["sharma_electricals"])
    finally:
        await engine.dispose()

    async for client in client_for(create_app(settings)):
        entities = (await client.get("/api/v1/entities")).json()
        assert "Sharma Electricals" in {e["display_name"] for e in entities}
        for as_of in (None, date(2026, 1, 31)):
            params = {"as_of": as_of.isoformat()} if as_of else {}
            body = (await client.get(url(SHARMA), params=params)).json()
            expected = compute_report(SHARMA, as_of or default_as_of(SHARMA)).model_dump(
                mode="json"
            )  # type: ignore[arg-type]
            # Sample ids may be listed in a different order; every number must be identical.
            for got, want in zip(body["metrics"], expected["metrics"], strict=True):
                assert (got["code"], got["value"], got["availability"], got["components"]) == (
                    want["code"],
                    want["value"],
                    want["availability"],
                    want["components"],
                )
            assert body["series"] == expected["series"]
            assert body["coverage"] == expected["coverage"]


async def test_metric_history_endpoint(client: httpx.AsyncClient) -> None:
    url = f"/api/v1/entities/{SHARMA.entity_id}/financial-metrics/history"
    body = (await client.get(url, params={"months": 6, "codes": ["debt.outstanding"]})).json()

    assert len(body["points"]) == 6 and set(body["points"][-1]["values"]) == {"debt.outstanding"}
    assert (await client.get(url, params={"codes": ["nope"]})).status_code == 404
    assert (await client.get(url, params={"months": 0})).status_code == 422
