"""Metric definitions and the helpers every metric uses to build its output.

A definition is the methodology of record: the ``method`` text is returned with every value and
served by ``GET /api/v1/meta/financial-metrics``. Changing how a metric is calculated means
bumping its ``version``.
"""

from __future__ import annotations

import statistics
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol
from uuid import UUID

from finpulse.analytics.schemas import (
    Availability,
    ComponentValue,
    Confidence,
    Metric,
    MetricDefinitionOut,
    Period,
    SourceRef,
    SourceTable,
    Unit,
)

QUANTUM: dict[Unit, Decimal] = {
    "INR": Decimal("0.01"),
    "ratio": Decimal("0.0001"),
    "days": Decimal("0.1"),
    "months": Decimal("0.1"),
    "score": Decimal("0.1"),
    "count": Decimal("1"),
}


@dataclass(frozen=True)
class MetricDef:
    code: str
    name: str
    family: str
    unit: Unit
    method: str
    version: int = 1

    def out(self) -> MetricDefinitionOut:
        return MetricDefinitionOut(
            code=self.code,
            name=self.name,
            family=self.family,
            unit=self.unit,
            version=self.version,
            method=self.method,
        )


CATALOGUE: dict[str, MetricDef] = {}


def define(
    code: str, name: str, family: str, unit: Unit, method: str, version: int = 1
) -> MetricDef:
    if code in CATALOGUE:
        raise ValueError(f"metric {code} defined twice")
    definition = MetricDef(code, name, family, unit, " ".join(method.split()), version)
    CATALOGUE[code] = definition
    return definition


# --- value helpers ------------------------------------------------------------------------------


def quantize(value: Decimal, unit: Unit) -> Decimal:
    return value.quantize(QUANTUM[unit], rounding=ROUND_HALF_UP)


def inr(minor: int) -> Decimal:
    """Minor units (paise) → rupees, exact."""
    return quantize(Decimal(minor) / 100, "INR")


def ratio(numerator: int | Decimal, denominator: int | Decimal) -> Decimal:
    return Decimal(numerator) / Decimal(denominator)


def coefficient_of_variation(values: Sequence[int]) -> Decimal | None:
    """Population standard deviation ÷ mean; None if the mean is not positive."""
    mean = Decimal(sum(values)) / len(values)
    if mean <= 0:
        return None
    return statistics.pstdev([Decimal(v) for v in values]) / mean


def months_confidence(have: int, want: int, minimum: int) -> Confidence | None:
    """High with the full intended window, medium with a shorter one, None below the minimum."""
    if have < minimum:
        return None
    return "high" if have >= want else "medium"


class _HasId(Protocol):
    @property
    def id(self) -> UUID: ...


def source(table: SourceTable, records: Iterable[_HasId], description: str) -> SourceRef:
    items = list(records)
    return SourceRef(
        table=table,
        record_count=len(items),
        description=description,
        sample_ids=[r.id for r in items[:5]],
    )


# --- metric builders ----------------------------------------------------------------------------


def available(
    d: MetricDef,
    value: Decimal,
    period: Period,
    *,
    confidence: Confidence = "high",
    components: dict[str, ComponentValue] | None = None,
    sources: Sequence[SourceRef] = (),
    notes: Sequence[str] = (),
) -> Metric:
    return Metric(
        code=d.code,
        name=d.name,
        family=d.family,
        value=quantize(value, d.unit),
        unit=d.unit,
        period=period,
        availability="available",
        confidence=confidence,
        method=d.method,
        components=components or {},
        sources=list(sources),
        notes=list(notes),
        version=d.version,
    )


def unavailable(
    d: MetricDef,
    period: Period,
    availability: Availability,
    reason: str,
    *,
    components: dict[str, ComponentValue] | None = None,
    sources: Sequence[SourceRef] = (),
) -> Metric:
    if availability == "available":
        raise ValueError("use available() for computed values")
    return Metric(
        code=d.code,
        name=d.name,
        family=d.family,
        value=None,
        unit=d.unit,
        period=period,
        availability=availability,
        confidence=None,
        method=d.method,
        components=components or {},
        sources=list(sources),
        notes=[reason],
        version=d.version,
    )


MetricFn = Callable[..., Metric]
