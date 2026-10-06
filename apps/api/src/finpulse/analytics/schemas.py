"""Typed outputs of the analytics engine. These are also the API response models."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Unit = Literal["INR", "ratio", "days", "months", "score", "count"]
Availability = Literal["available", "insufficient_data", "not_applicable"]
Confidence = Literal["high", "medium", "low"]
SourceTable = Literal[
    "transactions",
    "invoices",
    "invoice_payments",
    "bills",
    "bill_payments",
    "loans",
    "loan_installments",
    "counter_sales",
    "accounts",
]
ComponentValue = Decimal | int | str | None


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True)


class Period(_Model):
    start: date
    end: date
    label: str = Field(description='e.g. "2026-09", "trailing_3_months", "as_of"')


class SourceRef(_Model):
    """Which records a value was computed from."""

    table: SourceTable
    record_count: int
    description: str
    sample_ids: list[uuid.UUID] = Field(
        default_factory=list, description="Up to five contributing record ids, for drill-down"
    )


class Metric(_Model):
    code: str = Field(description='Stable identifier, e.g. "receivables.days"')
    name: str
    family: str
    value: Decimal | None = Field(
        description="Null unless availability is 'available'. INR values are rupees, exact to "
        "the paisa; ratios are fractions (0.25 = 25%)."
    )
    unit: Unit
    period: Period
    availability: Availability
    confidence: Confidence | None = Field(
        description="How much of the intended window and inputs the value rests on"
    )
    method: str = Field(description="How the value is calculated")
    components: dict[str, ComponentValue] = Field(
        default_factory=dict, description="Intermediate values and breakdowns"
    )
    sources: list[SourceRef] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    version: int


class SeriesPoint(_Model):
    period: Period
    value: Decimal | None


class MetricSeries(_Model):
    code: str
    name: str
    unit: Unit
    points: list[SeriesPoint]


class EntityRef(_Model):
    id: uuid.UUID
    display_name: str
    kind: str
    segment: str


class DataCoverage(_Model):
    first_transaction_on: date | None
    last_transaction_on: date | None
    complete_months: int = Field(description="Calendar months fully covered by the data")
    transaction_count: int
    invoice_count: int
    bill_count: int
    loan_count: int
    counter_sale_days: int
    uncategorised_transactions: int


class FinancialMetricsReport(_Model):
    entity: EntityRef
    as_of: date
    currency: str
    engine_version: str
    coverage: DataCoverage
    metrics: list[Metric]
    series: list[MetricSeries]


class MetricDefinitionOut(_Model):
    code: str
    name: str
    family: str
    unit: Unit
    version: int
    method: str
