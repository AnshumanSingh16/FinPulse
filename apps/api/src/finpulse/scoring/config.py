"""Load and validate a passport scoring configuration (``models/passport_v<N>.toml``).

The file is the methodology: weights, curves, bands and wording. It is validated strictly on
load — weights must sum to 1, curves must be increasing in value with points in 0–100, and every
factor must name a metric the analytics engine actually produces.
"""

from __future__ import annotations

import hashlib
import tomllib
from decimal import Decimal
from functools import lru_cache
from itertools import pairwise
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from finpulse.analytics.registry import CATALOGUE

MODELS_DIR = Path(__file__).parent / "models"
DEFAULT_MODEL = MODELS_DIR / "passport_v1.toml"
ONE = Decimal(1)
Points = Annotated[Decimal, Field(ge=0, le=100)]


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class FactorConfig(_Strict):
    metric: str
    weight: Annotated[Decimal, Field(gt=0, le=1)]
    breakpoints: list[tuple[Decimal, Points]]
    not_applicable_points: Points | None = None
    strength: str
    concern: str

    @field_validator("metric")
    @classmethod
    def _known_metric(cls, code: str) -> str:
        if code not in CATALOGUE:
            raise ValueError(f"unknown metric {code!r}")
        return code

    @field_validator("breakpoints")
    @classmethod
    def _increasing(cls, points: list[tuple[Decimal, Decimal]]) -> list[tuple[Decimal, Decimal]]:
        if len(points) < 2:
            raise ValueError("a curve needs at least two breakpoints")
        xs = [x for x, _ in points]
        if any(b <= a for a, b in pairwise(xs)):
            raise ValueError("breakpoint values must be strictly increasing")
        return points


class DimensionConfig(_Strict):
    name: str
    weight: Annotated[Decimal, Field(gt=0, le=1)]
    description: str
    factors: list[FactorConfig]

    @model_validator(mode="after")
    def _weights(self) -> DimensionConfig:
        if sum(f.weight for f in self.factors) != ONE:
            raise ValueError(f"{self.name}: factor weights must sum to 1")
        metrics = [f.metric for f in self.factors]
        if len(metrics) != len(set(metrics)):
            raise ValueError(f"{self.name}: a metric may appear once per dimension")
        return self


class BandConfig(_Strict):
    code: str
    label: str
    min_score: Points
    description: str


class ConfidenceConfig(_Strict):
    high: Annotated[Decimal, Field(ge=0, le=1)]
    medium: Annotated[Decimal, Field(ge=0, le=1)]
    low: Annotated[Decimal, Field(ge=0, le=1)]
    provisional_below: Annotated[Decimal, Field(ge=0, le=1)]


class ModelInfo(_Strict):
    id: str
    version: int
    name: str
    disclaimer: str


class ScoringModel(_Strict):
    model: ModelInfo
    confidence: ConfidenceConfig
    bands: list[BandConfig]
    dimensions: dict[str, DimensionConfig]
    sha256: str = ""  # of the source file, for traceability

    @model_validator(mode="after")
    def _consistent(self) -> ScoringModel:
        if sum(d.weight for d in self.dimensions.values()) != ONE:
            raise ValueError("dimension weights must sum to 1")
        mins = [b.min_score for b in self.bands]
        if not mins or mins != sorted(mins, reverse=True) or len(set(mins)) != len(mins):
            raise ValueError("bands must be listed highest first with distinct min_score")
        if mins[-1] != 0:
            raise ValueError("the last band must start at 0")
        return self

    def band_for(self, score: Decimal) -> BandConfig:
        return next(b for b in self.bands if score >= b.min_score)


def parse_model(text: str) -> ScoringModel:
    raw = tomllib.loads(text, parse_float=Decimal)
    raw["sha256"] = hashlib.sha256(text.encode()).hexdigest()
    return ScoringModel.model_validate(raw)


@lru_cache(maxsize=4)
def load_model(path: Path = DEFAULT_MODEL) -> ScoringModel:
    return parse_model(path.read_text(encoding="utf-8"))
