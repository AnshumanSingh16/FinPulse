from datetime import datetime

import httpx
import pytest

from finpulse import __version__


async def test_health_reports_service_identity(client: httpx.AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "finpulse-api"
    assert body["version"] == __version__
    assert body["environment"] == "test"
    assert datetime.fromisoformat(body["timestamp"]).tzinfo is not None


async def test_health_does_not_need_the_database(client: httpx.AsyncClient) -> None:
    # The test settings point at a port with nothing listening.
    assert (await client.get("/health")).status_code == 200


async def test_ready_is_503_when_database_is_unreachable(client: httpx.AsyncClient) -> None:
    response = await client.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    (check,) = body["checks"]
    assert check["name"] == "database"
    assert check["status"] == "failed"
    assert "finpulse:finpulse" not in (check["detail"] or "")


@pytest.mark.db
async def test_ready_is_200_with_a_reachable_database(db_client: httpx.AsyncClient) -> None:
    response = await db_client.get("/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"][0]["status"] == "ok"
    assert body["checks"][0]["latency_ms"] >= 0
