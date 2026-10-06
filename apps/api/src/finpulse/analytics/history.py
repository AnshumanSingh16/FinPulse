"""Metric values at each month-end: how every metric has moved, recomputed from the data as it
stood on each date (no look-ahead), so charts of receivables, debt or liquidity over time use
exactly the same definitions as the current report."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from finpulse.analytics.engine import compute_report
from finpulse.analytics.inputs import FinancialData
from finpulse.analytics.registry import CATALOGUE
from finpulse.analytics.schemas import EntityRef, MetricDefinitionOut
from finpulse.core.dates import add_months, month_end

MAX_HISTORY_MONTHS = 24


class MetricHistoryPoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    as_of: date
    values: dict[str, Decimal | None] = Field(description="Null where the metric is unavailable")


class MetricHistory(BaseModel):
    model_config = ConfigDict(frozen=True)

    entity: EntityRef
    metrics: list[MetricDefinitionOut]
    points: list[MetricHistoryPoint] = Field(description="Oldest first: month-ends, then as_of")


def month_end_dates(as_of: date, months: int, first: date) -> list[date]:
    """Month-ends before ``as_of`` (at most ``months`` points in all), then ``as_of``."""
    dates = [as_of]
    current = month_end(add_months(as_of, -1))
    while len(dates) < months and current >= first:
        dates.append(current)
        current = month_end(add_months(current, -1))
    return sorted(dates)


def metric_history(
    data: FinancialData, as_of: date, months: int, codes: list[str] | None = None
) -> MetricHistory:
    first = data.transactions[0].posted_on if data.transactions else as_of
    wanted = codes or list(CATALOGUE)
    points = []
    entity: EntityRef | None = None
    for day in month_end_dates(as_of, months, first):
        report = compute_report(data, day)
        entity = report.entity
        values = {m.code: m.value for m in report.metrics if m.code in wanted}
        points.append(MetricHistoryPoint(as_of=day, values=values))
    if entity is None:  # pragma: no cover - history_dates always includes as_of
        raise ValueError("no dates")
    return MetricHistory(entity=entity, metrics=[CATALOGUE[c].out() for c in wanted], points=points)
