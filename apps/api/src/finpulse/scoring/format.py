"""Render metric values for the plain-language explanations."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from finpulse.analytics.schemas import Unit
from finpulse.core.money import format_inr


def _q(value: Decimal, places: str) -> Decimal:
    return value.quantize(Decimal(places), rounding=ROUND_HALF_UP)


def format_value(value: Decimal | None, unit: Unit) -> str:
    if value is None:
        return "n/a"
    if unit == "INR":
        return format_inr(int(_q(value * 100, "1")))[:-3]  # whole rupees
    if unit == "ratio":
        return f"{_q(value * 100, '0.1')}%"
    if unit == "days":
        return f"{_q(value, '0.1')} days"
    if unit == "months":
        return f"{_q(value, '0.1')} months"
    if unit == "score":
        return f"{_q(value, '0.1')}/100"
    return str(_q(value, "1"))


def format_points(value: Decimal) -> str:
    return str(_q(value, "0.1"))


def signed(value: Decimal) -> str:
    q = _q(value, "0.1")
    return f"+{q}" if q > 0 else str(q)
