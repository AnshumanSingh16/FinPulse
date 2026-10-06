"""Typed Financial Passport outputs (also the API response models)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from finpulse.analytics.schemas import Availability, Confidence, EntityRef, Period, Unit

FactorStatus = Literal["scored", "scored_not_applicable", "excluded"]


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True)


class ModelRef(_Model):
    id: str
    version: int
    name: str
    config_sha256: str = Field(description="Hash of the scoring configuration that was used")


class FactorScore(_Model):
    """One metric's contribution. Every passport number traces back to these."""

    metric_code: str
    metric_name: str
    metric_value: Decimal | None
    metric_unit: Unit
    metric_period: Period
    metric_availability: Availability
    metric_confidence: Confidence | None
    status: FactorStatus
    points: Decimal | None = Field(description="0–100 from the factor's curve")
    weight: Decimal = Field(description="Configured weight within the dimension")
    effective_weight: Decimal = Field(description="Weight after re-normalising over scored factors")
    contribution_to_dimension: Decimal = Field(description="points × effective_weight")
    contribution_to_overall: Decimal = Field(
        description="Points this factor adds to the Financial Health score"
    )
    explanation: str


class DimensionScore(_Model):
    code: str
    name: str
    description: str
    score: Decimal | None = Field(description="0–100, or null if no factor could be scored")
    weight: Decimal
    effective_weight: Decimal
    confidence: Decimal = Field(description="0–1: share of the dimension resting on good data")
    factors: list[FactorScore]
    summary: str


class Band(_Model):
    code: str
    label: str
    description: str


class FinancialHealth(_Model):
    score: Decimal | None = Field(description="0–100 prototype Financial Health score")
    band: Band | None
    confidence: Decimal
    provisional: bool = Field(description="True when confidence is below the model's threshold")


class Driver(_Model):
    """A strength or concern: the factors pushing the score up or down the most."""

    kind: Literal["strength", "concern"]
    dimension: str
    metric_code: str
    impact: Decimal = Field(description="Points above (+) or below (−) a neutral 50 on this factor")
    text: str


class DimensionChange(_Model):
    code: str
    name: str
    from_score: Decimal | None
    to_score: Decimal | None
    delta: Decimal | None


class ChangeDriver(_Model):
    dimension: str
    metric_code: str
    metric_name: str
    from_value: Decimal | None
    to_value: Decimal | None
    from_points: Decimal | None
    to_points: Decimal | None
    impact: Decimal = Field(description="Change in this factor's contribution to the score")
    text: str


class ScoreChange(_Model):
    from_as_of: date
    to_as_of: date
    from_score: Decimal
    to_score: Decimal
    delta: Decimal
    from_band: str
    to_band: str
    dimensions: list[DimensionChange]
    drivers: list[ChangeDriver] = Field(description="Largest factor movements, biggest first")
    summary: str


class Passport(_Model):
    entity: EntityRef
    as_of: date
    model: ModelRef
    financial_health: FinancialHealth
    dimensions: list[DimensionScore]
    strengths: list[Driver]
    concerns: list[Driver]
    change_from_previous_month: ScoreChange | None = None
    analytics_engine_version: str
    disclaimer: str


class HistoryPoint(_Model):
    as_of: date
    score: Decimal | None
    band: str | None
    confidence: Decimal
    provisional: bool
    dimensions: dict[str, Decimal | None]


class PassportHistory(_Model):
    entity: EntityRef
    model: ModelRef
    points: list[HistoryPoint] = Field(description="Oldest first: month-ends, then as_of")
    changes: list[ScoreChange] = Field(description="Explanation of each step between points")
    summary: str
    disclaimer: str
