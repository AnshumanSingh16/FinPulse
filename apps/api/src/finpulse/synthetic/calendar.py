"""Date helpers for the generator (re-exported from ``finpulse.core.dates``)."""

from __future__ import annotations

from datetime import date

from finpulse.core.dates import add_months, clamp_day, days, month_end, month_index, month_start

__all__ = [
    "add_months",
    "clamp_day",
    "days",
    "financial_year_label",
    "month_end",
    "month_index",
    "month_start",
]


def financial_year_label(d: date) -> str:
    """Indian financial year (April–March), e.g. 2025-05-10 → '25-26'."""
    first = d.year if d.month >= 4 else d.year - 1
    return f"{first % 100:02d}-{(first + 1) % 100:02d}"
