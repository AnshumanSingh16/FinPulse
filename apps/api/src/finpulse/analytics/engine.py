"""Entry point: compute every financial metric for one entity as of one date.

Pure and deterministic — the same ``FinancialData`` and ``as_of`` always produce the same
report. No I/O, no clock, no LLM.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from finpulse.analytics.context import Context, month_label
from finpulse.analytics.inputs import FinancialData
from finpulse.analytics.metrics import ALL_METRICS
from finpulse.analytics.registry import CATALOGUE, MetricDef, inr
from finpulse.analytics.schemas import (
    DataCoverage,
    EntityRef,
    FinancialMetricsReport,
    MetricSeries,
    Period,
    SeriesPoint,
)
from finpulse.core.dates import month_end

ENGINE_VERSION = "1.0.0"
SERIES_MONTHS = 12


def default_as_of(data: FinancialData) -> date | None:
    """The latest date the data is complete for: ``data_through`` if known, else the last
    transaction date."""
    if data.data_through is not None:
        return data.data_through
    return data.transactions[-1].posted_on if data.transactions else None


def _series(ctx: Context, code: str, value_of: Callable[[date], int]) -> MetricSeries:
    d: MetricDef = CATALOGUE[code]
    return MetricSeries(
        code=code,
        name=d.name,
        unit=d.unit,
        points=[
            SeriesPoint(
                period=Period(start=m, end=month_end(m), label=month_label(m)),
                value=inr(value_of(m)),
            )
            for m in ctx.window(SERIES_MONTHS)
        ],
    )


def compute_report(data: FinancialData, as_of: date) -> FinancialMetricsReport:
    ctx = Context(data, as_of)
    return FinancialMetricsReport(
        entity=EntityRef(
            id=data.entity_id, display_name=data.display_name, kind=data.kind, segment=data.segment
        ),
        as_of=as_of,
        currency=data.currency,
        engine_version=ENGINE_VERSION,
        coverage=DataCoverage(
            first_transaction_on=ctx.first_date,
            last_transaction_on=ctx.txns[-1].posted_on if ctx.txns else None,
            complete_months=len(ctx.months),
            transaction_count=len(ctx.txns),
            invoice_count=len(ctx.invoices),
            bill_count=len(ctx.bills),
            loan_count=len(ctx.loans),
            counter_sale_days=len(ctx.counter_sales),
            uncategorised_transactions=sum(1 for t in ctx.txns if t.category is None),
        ),
        metrics=[fn(ctx) for fn in ALL_METRICS],
        series=[
            _series(ctx, "revenue.monthly", ctx.revenue),
            _series(ctx, "expenses.monthly", ctx.expenses),
            _series(ctx, "cashflow.net_monthly", ctx.net_cash_flow),
            MetricSeries(
                code="cash.balance",
                name="Month-end cash balance",
                unit="INR",
                points=[
                    SeriesPoint(
                        period=Period(start=month_end(m), end=month_end(m), label=month_label(m)),
                        value=inr(ctx.balance_at(month_end(m))),
                    )
                    for m in ctx.window(SERIES_MONTHS)
                ],
            ),
        ],
    )
