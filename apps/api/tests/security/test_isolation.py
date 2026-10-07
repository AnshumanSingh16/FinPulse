"""Data isolation between organisations, and the per-organisation running cap."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from tests.agents.fakes import FakeLLM, pack_for
from tests.security.helpers import (
    DEMO_ORG_ID,
    OTHER_ORG,
    GatedLLM,
    OrgSource,
    auth,
    keyed_client,
)
from tests.test_entities_api import ANANYA, MEHRA

SOURCE = OrgSource({DEMO_ORG_ID: [MEHRA], OTHER_ORG: [ANANYA]})


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async for c, _ in keyed_client(FakeLLM(pack_for("mehra_lighting")), SOURCE):
        yield c


async def test_another_organisations_entity_does_not_exist(client: httpx.AsyncClient) -> None:
    mine = (await client.get("/api/v1/entities", headers=auth("other"))).json()

    assert [e["id"] for e in mine] == [str(ANANYA.entity_id)]
    response = await client.get(
        f"/api/v1/entities/{MEHRA.entity_id}/passport", headers=auth("other")
    )
    assert response.status_code == 404


async def test_another_organisations_investigation_does_not_exist(
    client: httpx.AsyncClient,
) -> None:
    done = await client.post(
        f"/api/v1/entities/{MEHRA.entity_id}/investigate", headers=auth("analyst")
    )
    inv = done.json()["investigation_id"]

    for path in ("", "/events", "/audit"):
        own = await client.get(f"/api/v1/investigations/{inv}{path}", headers=auth("analyst"))
        theirs = await client.get(f"/api/v1/investigations/{inv}{path}", headers=auth("other"))
        assert own.status_code == 200, path
        assert theirs.status_code == 404, path
    assert (await client.get("/api/v1/investigations", headers=auth("other"))).json() == []


async def test_background_progress_is_scoped_too(client: httpx.AsyncClient) -> None:
    started = await client.post(
        f"/api/v1/entities/{MEHRA.entity_id}/investigations", headers=auth("analyst")
    )
    inv = started.json()["investigation_id"]

    theirs = await client.get(f"/api/v1/investigations/{inv}/progress", headers=auth("other"))

    assert theirs.status_code == 404


async def test_running_investigations_are_capped_per_organisation() -> None:
    llm = GatedLLM(FakeLLM(pack_for("mehra_lighting")))
    async for c, _ in keyed_client(llm, SOURCE, INVESTIGATIONS_MAX_RUNNING=1):
        start = f"/api/v1/entities/{MEHRA.entity_id}/investigations"
        first = await c.post(start, headers=auth("analyst"))
        assert first.status_code == 202

        second = await c.post(start, headers=auth("analyst"))
        assert second.status_code == 429
        assert second.json()["code"] == "too_many_investigations"
        # another organisation has its own allowance
        other = await c.post(
            f"/api/v1/entities/{ANANYA.entity_id}/investigations", headers=auth("other")
        )
        assert other.status_code == 202

        llm.gate.set()
        await _finish(c, first.json()["investigation_id"], "analyst")
        third = await c.post(start, headers=auth("analyst"))
        assert third.status_code == 202
        await _finish(c, third.json()["investigation_id"], "analyst")


async def _finish(c: httpx.AsyncClient, inv: str, who: str) -> dict[str, Any]:
    for _ in range(300):
        body: dict[str, Any] = (
            await c.get(f"/api/v1/investigations/{inv}/progress", headers=auth(who))
        ).json()
        if body["status"] != "running":
            return body
        await asyncio.sleep(0.02)
    raise AssertionError("did not finish")
