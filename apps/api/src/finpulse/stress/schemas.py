"""Typed stress-test outputs (also the API response models)."""

from __future__ import annotations

import datetime as dt
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from finpulse.analytics.schemas import EntityRef, SourceRef
from finpulse.scoring.schemas import ChangeDriver, DimensionChange

RiskCode = Literal["low", "elevated", "high", "critical"]
EvidenceKind = Literal["baseline", "shock", "outcome"]


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True)


class ProjectedMonth(_Model):
    month: date
    label: str
    revenue: Decimal = Field(description="Sales excluding GST (accrual)")
    expenses: Decimal = Field(description="Purchases excluding GST + operating costs (accrual)")
    money_in: Decimal = Field(description="All cash in, including any new loan")
    money_out: Decimal = Field(description="All cash out")
    debt_service: Decimal
    overdraft_interest: Decimal
    net_cash_flow: Decimal
    closing_balance: Decimal
    available_funds: Decimal = Field(description="Closing balance + overdraft limit")
    funds_exhausted: bool


class FailurePoint(_Model):
    date: dt.date = Field(description="Estimated day available funds run out (flows spread evenly)")
    month: str
    months_from_as_of: Decimal
    shortfall_at_month_end: Decimal = Field(description="Amount beyond the overdraft limit")


class RiskAssessment(_Model):
    level: RiskCode
    label: str
    reasons: list[str]


class Projection(_Model):
    """One simulated path: the baseline (no shock) or the scenario."""

    revenue: Decimal = Field(description="Total over the horizon")
    expenses: Decimal
    net_cash_flow: Decimal
    closing_balance: Decimal
    minimum_balance: Decimal
    minimum_balance_month: str
    liquidity_ratio: Decimal | None
    cash_runway_months: Decimal | None = Field(
        description="Available funds at as_of ÷ average monthly net outflow; null when not burning"
    )
    peak_overdraft_utilisation: Decimal | None
    financial_health_score: Decimal | None
    financial_health_band: str | None
    risk: RiskAssessment
    failure_point: FailurePoint | None
    months: list[ProjectedMonth]


class Comparison(_Model):
    key: str
    label: str
    unit: Literal["INR", "ratio", "months", "score"]
    baseline: Decimal | None
    scenario: Decimal | None
    absolute_change: Decimal | None
    percentage_change: Decimal | None = Field(
        description="Change ÷ |baseline|, as a fraction; null when baseline is zero or missing"
    )
    direction: Literal["better", "worse", "unchanged", "n/a"]


class RiskChange(_Model):
    baseline: RiskCode
    scenario: RiskCode
    steps: int = Field(description="Levels moved: + worse, − better")
    escalated: bool
    summary: str


class HealthImpact(_Model):
    current_score: Decimal | None = Field(description="Today's passport from actual data")
    baseline_projected_score: Decimal | None
    scenario_score: Decimal | None
    change: Decimal | None
    baseline_band: str | None
    scenario_band: str | None
    dimensions: list[DimensionChange]
    drivers: list[ChangeDriver]
    summary: str


class Evidence(_Model):
    """A citable fact: every number an explanation may use, with where it came from."""

    id: str
    kind: EvidenceKind
    text: str
    values: dict[str, Decimal | int | str | None] = Field(default_factory=dict)
    metric_codes: list[str] = Field(default_factory=list)
    sources: list[SourceRef] = Field(default_factory=list)


class AppliedShock(_Model):
    type: str
    name: str
    parameters: dict[str, Any] = Field(description="As applied, defaults resolved")
    description: str


class ScenarioInfo(_Model):
    preset: str | None
    name: str
    shocks: list[AppliedShock]


class StressTestResult(_Model):
    entity: EntityRef
    as_of: date
    horizon_months: int
    projection_start: date
    scenario: ScenarioInfo
    baseline: Projection
    stressed: Projection
    comparisons: list[Comparison]
    risk_change: RiskChange
    health_impact: HealthImpact
    evidence: list[Evidence]
    engine_version: str
    disclaimer: str


class ShockTypeOut(_Model):
    type: str
    name: str
    description: str
    parameters_schema: dict[str, Any]


class PresetOut(_Model):
    code: str
    name: str
    shocks: list[dict[str, Any]]


class ScenarioCatalogue(_Model):
    shock_types: list[ShockTypeOut]
    presets: list[PresetOut]
