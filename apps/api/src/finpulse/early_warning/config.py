"""Load and validate the early-warning configuration (``config/early_warning_v<N>.toml``).

Every threshold, window and severity weight lives in that file; the rules contain logic only.
Validation is strict: each rule's section must match the rule's parameter model exactly (no
missing or unknown keys), severity tiers must be ordered in the rule's direction, and every
registered rule must be configured — there are no hidden defaults in code.
"""

from __future__ import annotations

import hashlib
import tomllib
from decimal import Decimal
from functools import lru_cache
from itertools import pairwise
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CONFIG_DIR = Path(__file__).parent / "config"
DEFAULT_CONFIG = CONFIG_DIR / "early_warning_v1.toml"

Severity = Literal["low", "medium", "high", "critical"]
SEVERITIES: tuple[Severity, ...] = ("low", "medium", "high", "critical")
Direction = Literal["above", "below"]  # warn when the measure is at/above (or at/below) a tier


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Tiers(_Strict):
    """The measure value at which each severity starts. Omitted tiers are never assigned."""

    low: Decimal | None = None
    medium: Decimal | None = None
    high: Decimal | None = None
    critical: Decimal | None = None

    def defined(self) -> list[tuple[Severity, Decimal]]:
        return [(s, v) for s in SEVERITIES if (v := getattr(self, s)) is not None]

    def check(self, direction: Direction) -> None:
        values = [v for _, v in self.defined()]
        if not values:
            raise ValueError("at least one severity tier is required")
        ordered = all(b > a if direction == "above" else b < a for a, b in pairwise(values))
        if not ordered:
            raise ValueError(
                "tiers must strictly "
                + ("increase" if direction == "above" else "decrease")
                + " from low to critical"
            )

    def grade(self, value: Decimal, direction: Direction) -> Severity | None:
        """The highest severity whose tier the value reaches."""
        hit: Severity | None = None
        for severity, tier in self.defined():
            if (value >= tier) if direction == "above" else (value <= tier):
                hit = severity
        return hit


class RuleParams(_Strict):
    """Settings every rule has; rules extend this with their own windows and limits."""

    enabled: bool
    tiers: Tiers


class ConfigInfo(_Strict):
    id: str
    version: int
    name: str
    disclaimer: str


class SeverityPoints(_Strict):
    low: Annotated[int, Field(ge=0)]
    medium: Annotated[int, Field(ge=0)]
    high: Annotated[int, Field(ge=0)]
    critical: Annotated[int, Field(ge=0)]


class SummaryConfig(_Strict):
    points: SeverityPoints
    # Early-warning index (0–100) at which the overall risk level starts.
    levels: Tiers
    timeline_months: Annotated[int, Field(ge=1, le=24)]
    compare_months: Annotated[int, Field(ge=1, le=12)]
    top_warnings: Annotated[int, Field(ge=1, le=20)]
    streak_months: Annotated[int, Field(ge=1, le=24)]


class EarlyWarningConfig(_Strict):
    config: ConfigInfo
    summary: SummaryConfig
    rules: dict[str, Any]  # raw sections; validated against each rule's Params below
    sha256: str = ""

    @model_validator(mode="after")
    def _rules(self) -> EarlyWarningConfig:
        from finpulse.early_warning.rules import RULES  # the registry imports this module

        self.summary.levels.check("above")
        unknown = set(self.rules) - set(RULES)
        missing = set(RULES) - set(self.rules)
        if unknown:
            raise ValueError(f"unknown rules in config: {sorted(unknown)}")
        if missing:
            raise ValueError(f"rules missing from config: {sorted(missing)}")
        parsed: dict[str, Any] = {}
        for code, raw in self.rules.items():
            rule = RULES[code]
            try:
                params = rule.Params.model_validate(raw)
                params.tiers.check(rule.direction)
            except ValueError as exc:
                raise ValueError(f"rules.{code}: {exc}") from exc
            parsed[code] = params
        object.__setattr__(self, "rules", parsed)
        return self

    def params(self, code: str) -> Any:
        return self.rules[code]


def parse_config(text: str) -> EarlyWarningConfig:
    raw = tomllib.loads(text, parse_float=Decimal)
    raw["sha256"] = hashlib.sha256(text.encode()).hexdigest()
    return EarlyWarningConfig.model_validate(raw)


@lru_cache(maxsize=4)
def load_config(path: Path = DEFAULT_CONFIG) -> EarlyWarningConfig:
    return parse_config(path.read_text(encoding="utf-8"))
