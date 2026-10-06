"""Build analytics reports with chosen metric values, for hand-checkable scoring tests."""

import uuid
from datetime import date
from decimal import Decimal

from finpulse.analytics.registry import CATALOGUE, available, unavailable
from finpulse.analytics.schemas import (
    Confidence,
    DataCoverage,
    EntityRef,
    FinancialMetricsReport,
    Metric,
    Period,
)
from finpulse.scoring.config import ScoringModel, parse_model

NA = "not_applicable"
AS_OF = date(2026, 6, 30)
PERIOD = Period(start=date(2026, 1, 1), end=AS_OF, label="test")

TINY_MODEL = """
[model]
id = "tiny"
version = 1
name = "Tiny test model"
disclaimer = "Test model. Not a credit score."

[confidence]
high = 1.0
medium = 0.75
low = 0.5
provisional_below = 0.7

[[bands]]
code = "good"
label = "Good"
min_score = 70
description = "Good."

[[bands]]
code = "poor"
label = "Poor"
min_score = 0
description = "Poor."

[dimensions.alpha]
name = "Alpha"
weight = 0.6
description = "First."

[[dimensions.alpha.factors]]
metric = "revenue.volatility"
weight = 0.5
breakpoints = [[0, 100], [1, 0]]
strength = "Steady revenue"
concern = "Volatile revenue"

[[dimensions.alpha.factors]]
metric = "income.stability"
weight = 0.5
breakpoints = [[0, 0], [100, 100]]
strength = "Stable income"
concern = "Unstable income"

[dimensions.beta]
name = "Beta"
weight = 0.4
description = "Second."

[[dimensions.beta.factors]]
metric = "debt.leverage"
weight = 0.5
breakpoints = [[0, 100], [1, 0]]
strength = "Low debt"
concern = "High debt"

[[dimensions.beta.factors]]
metric = "cash.runway"
weight = 0.5
not_applicable_points = 100
breakpoints = [[0, 0], [12, 100]]
strength = "Long runway"
concern = "Short runway"
"""


def tiny_model() -> ScoringModel:
    return parse_model(TINY_MODEL)


Value = Decimal | int | float | str | None


def metric(code: str, value: Value, confidence: Confidence = "high") -> Metric:
    d = CATALOGUE[code]
    if value is None:
        return unavailable(d, PERIOD, "insufficient_data", "Not enough data.")
    if value == NA:
        return unavailable(d, PERIOD, "not_applicable", "Not burning cash.")
    return available(d, Decimal(str(value)), PERIOD, confidence=confidence)


def report(
    values: dict[str, Value],
    confidence: dict[str, Confidence] | None = None,
    as_of: date = AS_OF,
) -> FinancialMetricsReport:
    """Every catalogue metric; those not given are insufficient_data."""
    confidence = confidence or {}
    return FinancialMetricsReport(
        entity=EntityRef(id=uuid.UUID(int=7), display_name="Test", kind="business", segment="t"),
        as_of=as_of,
        currency="INR",
        engine_version="test",
        coverage=DataCoverage(
            first_transaction_on=None,
            last_transaction_on=None,
            complete_months=6,
            transaction_count=0,
            invoice_count=0,
            bill_count=0,
            loan_count=0,
            counter_sale_days=0,
            uncategorised_transactions=0,
        ),
        metrics=[
            metric(code, values.get(code), confidence.get(code, "high")) for code in CATALOGUE
        ],
        series=[],
    )
