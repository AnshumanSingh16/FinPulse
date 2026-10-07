"""Shared fixtures for the security tests: keyed apps, two organisations, a gated model."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx

from finpulse.agents.llm import LLMRequest, LLMResponse
from finpulse.analytics.inputs import FinancialData
from finpulse.api.deps import get_financial_data_source, get_llm_client
from finpulse.api.schemas.entities import EntitySummary
from finpulse.core.security import DEMO_ORG_ID, hash_key
from finpulse.main import create_app
from tests.conftest import client_for, make_settings

OTHER_ORG = uuid.UUID("00000000-0000-4000-8000-0000000000b2")
KEYS = {
    "viewer": "fpk_test_viewer_key_000000000000000000000",
    "analyst": "fpk_test_analyst_key_00000000000000000000",
    "admin": "fpk_test_admin_key_0000000000000000000000",
    "other": "fpk_test_other_org_analyst_0000000000000",
}
API_KEYS = ",".join(
    [
        f"v:viewer:{hash_key(KEYS['viewer'])}",
        f"a:analyst:{hash_key(KEYS['analyst'])}",
        f"root:admin:{hash_key(KEYS['admin'])}",
        f"b:analyst:{hash_key(KEYS['other'])}:{OTHER_ORG}",
    ]
)


def auth(who: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {KEYS[who]}"}


class OrgSource:
    """Entities per organisation, like the real repository (which filters by org_id)."""

    def __init__(self, by_org: dict[uuid.UUID, list[FinancialData]]) -> None:
        self.by_org = {org: {e.entity_id: e for e in es} for org, es in by_org.items()}

    async def list_entities(self, org_id: uuid.UUID) -> list[EntitySummary]:
        return [
            EntitySummary(
                id=e.entity_id,
                display_name=e.display_name,
                kind=e.kind,
                segment=e.segment,
                data_origin="synthetic",
            )
            for e in self.by_org.get(org_id, {}).values()
        ]

    async def load(self, org_id: uuid.UUID, entity_id: uuid.UUID) -> FinancialData | None:
        return self.by_org.get(org_id, {}).get(entity_id)


class GatedLLM:
    """Wraps a model and holds every call until ``gate`` is set (to keep runs 'running')."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.model = inner.model
        self.gate = asyncio.Event()

    async def complete(self, request: LLMRequest) -> LLMResponse:
        await self.gate.wait()
        return await self.inner.complete(request)  # type: ignore[no-any-return]


async def keyed_client(
    llm: Any, source: Any, **settings: object
) -> AsyncIterator[tuple[httpx.AsyncClient, Any]]:
    app = create_app(make_settings(API_KEYS=API_KEYS, **settings))
    app.dependency_overrides[get_financial_data_source] = lambda: source
    app.dependency_overrides[get_llm_client] = lambda: llm
    async for c in client_for(app):
        yield c, app


__all__ = ["DEMO_ORG_ID", "OTHER_ORG", "GatedLLM", "OrgSource", "auth", "keyed_client"]
