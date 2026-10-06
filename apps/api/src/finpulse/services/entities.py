"""Shared steps for any endpoint that analyses one entity."""

from __future__ import annotations

import uuid
from datetime import date

from finpulse.analytics import default_as_of
from finpulse.analytics.inputs import FinancialData
from finpulse.core.errors import NotFoundError, UnprocessableError
from finpulse.persistence.repositories.financial_data import FinancialDataSource


async def load_entity(
    source: FinancialDataSource, org_id: uuid.UUID, entity_id: uuid.UUID
) -> FinancialData:
    data = await source.load(org_id, entity_id)
    if data is None:
        raise NotFoundError(f"No entity with id {entity_id}.", code="entity_not_found")
    return data


def resolve_as_of(data: FinancialData, as_of: date | None) -> date:
    """The requested date, or the end of the data; there must be data on or before it."""
    effective = as_of or default_as_of(data)
    if effective is None or not data.transactions or effective < data.transactions[0].posted_on:
        first = data.transactions[0].posted_on if data.transactions else None
        raise UnprocessableError(
            "There is no financial data on or before the requested date."
            + (f" The history starts on {first}." if first else ""),
            code="insufficient_history",
        )
    return effective
