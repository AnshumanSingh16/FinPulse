"""Typed outputs of the early-warning engine. These are also the API response models."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from finpulse.analytics.schemas import EntityRef, Period, SourceRef, Unit
from finpulse.early_warning.config import Direction, Severity

Category = Literal[
    "revenue",
    "expenses",
    "cash",
    "liquidity",
    "receivables",
    "debt",
    "concentration",
    "transactions",
    "volatility",
]
Trend = Literal["deteriorating", "persistent"]
Status = Literal["new", "ongoing", "escalated", "easing"]
RuleState = Literal["triggered", "clear", "insufficient_data", "not_applicable", "disabled"]
RiskLevel = Literal["none", "low", "medium", "high", "critical"]


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True)


class MetricRef(_Model):
    code: str
    name: str
    unit: Unit
    derived: bool = Field(
        description="True when the value is computed by the rule itself rather than taken from "
        "the financial-metrics catalogue"
    )


class Threshold(_Model):
    """The configured limit this warning crossed, and all the rule's tiers for context."""

    measure: str = Field(description="What is compared with the tiers")
    observed: Decimal
    operator: Literal[">=", "<="]
    value: Decimal = Field(description="The tier that was crossed")
    unit: Unit
    tier: Severity = Field(description="Severity of the crossed tier before any trend downgrade")
    tiers: dict[str, Decimal] = Field(description="The configured tiers, before scaling")
    scale: Decimal = Field(
        description="Tiers are multiplied by this (≥ 1) for entities whose revenue normally "
        "varies more than the configured norm; 1 = no scaling"
    )
    direction: Direction


class WarningEvidence(_Model):
    id: str
    text: str
    values: dict[str, Decimal | int | str | None] = Field(default_factory=dict)
    metric_codes: list[str] = Field(default_factory=list)
    period: Period | None = None
    sources: list[SourceRef] = Field(default_factory=list)


class EarlyWarning(_Model):
    id: str = Field(description="Stable while the condition persists: rule + entity + onset")
    rule: str
    category: Category
    severity: Severity
    title: str
    description: str
    affected_metric: MetricRef
    current_value: Decimal | None
    previous_value: Decimal | None
    change: Decimal | None = Field(description="current − previous, in the metric's unit")
    change_pct: Decimal | None = Field(description="(current − previous) ÷ |previous|")
    current_period: Period
    previous_period: Period | None
    threshold: Threshold
    trend: Trend = Field(
        description="persistent = the condition is present but not getting worse; such warnings "
        "are one severity lower than their tier"
    )
    status: Status = Field(description="Compared with the previous month-end")
    first_detected_on: dt.date = Field(
        description="Start of the current unbroken run of month-ends with this warning"
    )
    detected_at: dt.datetime = Field(
        description="Data time of detection: the end of the as_of day (IST). Deterministic — the "
        "same data always gives the same timestamp"
    )
    evidence: list[WarningEvidence]


class RuleOutcome(_Model):
    rule: str
    category: Category
    state: RuleState
    reason: str | None = None


class ConfigRef(_Model):
    id: str
    version: int
    sha256: str


class WarningsReport(_Model):
    entity: EntityRef
    as_of: dt.date
    engine_version: str
    config: ConfigRef
    warnings: list[EarlyWarning]
    rules: list[RuleOutcome]
    disclaimer: str


class WarningBrief(_Model):
    id: str
    rule: str
    category: Category
    severity: Severity
    title: str
    first_detected_on: dt.date


class SeverityCounts(_Model):
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    total: int = 0


class CategoryRisk(_Model):
    category: Category
    label: str
    severity: Severity
    warnings: int
    rules: list[str]


class TimelinePoint(_Model):
    as_of: dt.date
    level: RiskLevel
    index: int
    counts: SeverityCounts
    rules: list[str]


class RiskTrend(_Model):
    compared_with: dt.date | None
    previous_level: RiskLevel | None
    previous_index: int | None
    direction: Literal["worsening", "improving", "stable", "unknown"]
    new: list[str]
    resolved: list[str]
    escalated: list[str]
    eased: list[str]


class RiskSummary(_Model):
    entity: EntityRef
    as_of: dt.date
    engine_version: str
    config: ConfigRef
    risk_level: RiskLevel
    early_warning_index: int = Field(
        ge=0, le=100, description="Sum of configured points per warning severity, capped at 100"
    )
    headline: str
    counts: SeverityCounts
    categories: list[CategoryRisk]
    top_warnings: list[WarningBrief]
    trend: RiskTrend
    first_warning_on: dt.date | None = Field(
        description="Start of the current unbroken run of month-ends with at least one warning"
    )
    timeline: list[TimelinePoint]
    rules_evaluated: int
    rules_triggered: int
    disclaimer: str


class RuleInfo(_Model):
    code: str
    category: Category
    about: str
    affected_metric: MetricRef
    direction: Direction
    parameters: dict[str, object] = Field(description="The configured thresholds and windows")


class RuleCatalogue(_Model):
    config: ConfigRef
    name: str
    disclaimer: str
    severity_points: dict[str, int]
    risk_levels: dict[str, Decimal]
    rules: list[RuleInfo]
