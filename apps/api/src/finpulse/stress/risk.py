"""Deterministic risk levels for a projection. Thresholds are the policy; tests pin them."""

from __future__ import annotations

from decimal import Decimal

from finpulse.stress.projection import Simulation
from finpulse.stress.schemas import RiskAssessment, RiskCode

LEVELS: tuple[RiskCode, ...] = ("low", "elevated", "high", "critical")
LABELS = {"low": "Low", "elevated": "Elevated", "high": "High", "critical": "Critical"}

HIGH_RUNWAY_MONTHS = Decimal(3)
ELEVATED_RUNWAY_MONTHS = Decimal(6)
HIGH_OVERDRAFT_UTILISATION = Decimal("0.85")
HIGH_MIN_FUNDS_MONTHS = Decimal("0.5")  # lowest available funds vs a month of outflows
ELEVATED_LIQUIDITY = Decimal("0.5")


def assess(sim: Simulation) -> RiskAssessment:
    """critical: available funds (incl. overdraft) run out within the horizon.
    high: runway under 3 months, overdraft ≥ 85% used, or lowest available funds under half a
          month of outflows.
    elevated: the balance goes negative (overdraft used), runway under 6 months, or the
              end-of-horizon liquidity ratio is under 0.5.
    low: none of the above."""
    critical, high, elevated = [], [], []
    if sim.failure is not None:
        critical.append(
            f"Available funds, including the overdraft, run out around {sim.failure.day}."
        )
    runway = sim.runway_months()
    if runway is not None and runway < HIGH_RUNWAY_MONTHS:
        high.append(f"Cash runway of {runway.quantize(Decimal('0.1'))} months is under 3.")
    elif runway is not None and runway < ELEVATED_RUNWAY_MONTHS:
        elevated.append(f"Cash runway of {runway.quantize(Decimal('0.1'))} months is under 6.")
    peak = sim.peak_overdraft_utilisation()
    if peak is not None and peak >= HIGH_OVERDRAFT_UTILISATION:
        used = (peak * 100).quantize(Decimal("1"))
        high.append(
            f"Overdraft need reaches {used}% of the limit."
            if peak > 1
            else f"The overdraft reaches {used}% of its limit."
        )
    low_point = sim.minimum
    funds = Decimal(low_point.closing_balance + sim.baseline.overdraft_limit)
    if funds < HIGH_MIN_FUNDS_MONTHS * sim.average_outflows() and sim.failure is None:
        high.append(
            f"Available funds fall to under half a month of outgoings in {low_point.month:%b %Y}."
        )
    if low_point.closing_balance < 0:
        elevated.append(f"The account goes overdrawn, at its lowest in {low_point.month:%b %Y}.")
    ratio, _ = sim.liquidity()
    if ratio is not None and ratio < ELEVATED_LIQUIDITY:
        elevated.append(f"Liquidity ratio ends at {ratio.quantize(Decimal('0.01'))}, under 0.5.")

    level: RiskCode = (
        "critical" if critical else "high" if high else "elevated" if elevated else "low"
    )
    reasons = critical + high + elevated or ["No risk thresholds are crossed within the horizon."]
    return RiskAssessment(level=level, label=LABELS[level], reasons=reasons)


def steps(a: RiskCode, b: RiskCode) -> int:
    return LEVELS.index(b) - LEVELS.index(a)
