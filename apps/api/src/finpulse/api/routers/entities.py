"""Entities and their financial metrics.

Every number here is calculated by the deterministic analytics engine at request time from the
entity's stored records; nothing is estimated by a model.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Path, Query

from finpulse.analytics import CATALOGUE, compute_report
from finpulse.analytics.schemas import FinancialMetricsReport, Metric, MetricDefinitionOut
from finpulse.api.deps import DataSourceDep, OrgDep
from finpulse.api.schemas.entities import EntitySummary
from finpulse.core.errors import NotFoundError
from finpulse.services.entities import load_entity, resolve_as_of

router = APIRouter(prefix="/api/v1")

AsOf = Annotated[
    date | None,
    Query(description="Calculate as at the end of this day. Defaults to the end of the data."),
]
EntityId = Annotated[uuid.UUID, Path(description="Entity (subject) id")]


async def _report(
    source: DataSourceDep, org_id: uuid.UUID, entity_id: uuid.UUID, as_of: date | None
) -> FinancialMetricsReport:
    data = await load_entity(source, org_id, entity_id)
    return compute_report(data, resolve_as_of(data, as_of))


@router.get("/entities", response_model=list[EntitySummary], tags=["entities"])
async def list_entities(source: DataSourceDep, org_id: OrgDep) -> list[EntitySummary]:
    return await source.list_entities(org_id)


@router.get(
    "/entities/{entity_id}/financial-metrics",
    response_model=FinancialMetricsReport,
    tags=["analytics"],
    summary="All financial metrics for an entity",
)
async def financial_metrics(
    entity_id: EntityId, source: DataSourceDep, org_id: OrgDep, as_of: AsOf = None
) -> FinancialMetricsReport:
    return await _report(source, org_id, entity_id, as_of)


@router.get(
    "/entities/{entity_id}/financial-metrics/{metric_code}",
    response_model=Metric,
    tags=["analytics"],
    summary="One financial metric for an entity",
)
async def financial_metric(
    entity_id: EntityId,
    metric_code: Annotated[str, Path(description='e.g. "receivables.days"')],
    source: DataSourceDep,
    org_id: OrgDep,
    as_of: AsOf = None,
) -> Metric:
    if metric_code not in CATALOGUE:
        raise NotFoundError(
            f"Unknown metric {metric_code!r}.",
            code="metric_not_found",
            extra={"known": sorted(CATALOGUE)},
        )
    report = await _report(source, org_id, entity_id, as_of)
    return next(m for m in report.metrics if m.code == metric_code)


@router.get(
    "/meta/financial-metrics",
    response_model=list[MetricDefinitionOut],
    tags=["meta"],
    summary="Definitions of every financial metric (methodology)",
)
async def metric_catalogue() -> list[MetricDefinitionOut]:
    return [d.out() for d in CATALOGUE.values()]
