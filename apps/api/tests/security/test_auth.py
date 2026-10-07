"""Authentication and roles (SECURITY.md §2)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

from finpulse.core.security import authenticate, hash_key, parse_api_keys
from finpulse.main import create_app
from tests.agents.fakes import FakeLLM, pack_for
from tests.conftest import make_settings
from tests.security.helpers import API_KEYS, DEMO_ORG_ID, KEYS, OrgSource, auth, keyed_client
from tests.test_entities_api import MEHRA

ENTITY = f"/api/v1/entities/{MEHRA.entity_id}"


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    source = OrgSource({DEMO_ORG_ID: [MEHRA]})
    async for c, _ in keyed_client(FakeLLM(pack_for("mehra_lighting")), source):
        yield c


async def test_requests_without_a_key_are_refused(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/entities")

    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"
    assert response.headers["www-authenticate"] == "Bearer"


async def test_a_wrong_key_is_refused_without_saying_why(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/entities", headers={"Authorization": "Bearer fpk_nope"})

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_api_key"
    assert KEYS["viewer"] not in response.text


async def test_x_api_key_header_is_accepted(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/entities", headers={"X-API-Key": KEYS["viewer"]})

    assert response.status_code == 200


async def test_health_stays_public(client: httpx.AsyncClient) -> None:
    assert (await client.get("/health")).status_code == 200


async def test_viewers_read_but_cannot_start_investigations(client: httpx.AsyncClient) -> None:
    assert (await client.get(f"{ENTITY}/passport", headers=auth("viewer"))).status_code == 200

    response = await client.post(f"{ENTITY}/investigate", headers=auth("viewer"))

    assert response.status_code == 403
    assert response.json()["code"] == "insufficient_role"


async def test_analysts_investigate_but_cannot_reset_the_demo(client: httpx.AsyncClient) -> None:
    assert (await client.post(f"{ENTITY}/investigate", headers=auth("analyst"))).status_code == 200

    response = await client.post("/api/v1/demo/reset", headers=auth("analyst"), json={})

    assert response.status_code == 403


def test_keys_are_configured_as_hashes_and_compared_by_hash() -> None:
    keys = parse_api_keys(API_KEYS)

    assert all(KEYS["viewer"] not in k.sha256 for k in keys)
    found = authenticate(KEYS["admin"], keys)
    assert found is not None and found.role == "admin"
    assert authenticate("fpk_" + "x" * 43, keys) is None


@pytest.mark.parametrize(
    "raw",
    ["web:analyst", "web:root:" + "a" * 64, "web:viewer:nothex", f"w:viewer:{'a' * 64}:not-a-uuid"],
)
def test_malformed_key_entries_are_rejected(raw: str) -> None:
    with pytest.raises(ValueError) as caught:
        parse_api_keys(raw)
    assert "a" * 64 not in str(caught.value)


@pytest.mark.parametrize("env", ["staging", "production"])
def test_production_refuses_to_start_without_keys(env: str) -> None:
    with pytest.raises(RuntimeError, match="API_KEYS"):
        create_app(make_settings(FINPULSE_ENV=env, AUDIT_BACKEND="postgres"))


def test_production_refuses_an_in_memory_audit_trail() -> None:
    key = f"ops:admin:{hash_key('fpk_x')}"
    with pytest.raises(RuntimeError, match="AUDIT_BACKEND"):
        create_app(make_settings(FINPULSE_ENV="production", API_KEYS=key, AUDIT_BACKEND="memory"))


def test_production_refuses_wildcard_cors() -> None:
    key = f"ops:admin:{hash_key('fpk_x')}"
    with pytest.raises(ValueError, match="CORS"):  # refused by the settings validator
        create_app(
            make_settings(
                FINPULSE_ENV="production",
                API_KEYS=key,
                AUDIT_BACKEND="postgres",
                CORS_ALLOWED_ORIGINS="*",
            )
        )
