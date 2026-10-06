"""Date helpers. Nothing here reads the clock."""

from __future__ import annotations

import calendar
from collections.abc import Iterator
from datetime import date, timedelta


def add_months(d: date, months: int) -> date:
    index = d.year * 12 + (d.month - 1) + months
    year, month0 = divmod(index, 12)
    return clamp_day(year, month0 + 1, d.day)


def clamp_day(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def month_start(d: date) -> date:
    return d.replace(day=1)


def month_end(d: date) -> date:
    return clamp_day(d.year, d.month, 31)


def month_index(start: date, d: date) -> int:
    """0 for the month containing ``start``, 1 for the next, …"""
    return (d.year - start.year) * 12 + (d.month - start.month)


def days(start: date, end: date) -> Iterator[date]:
    """Inclusive range of days."""
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def financial_year_label(d: date) -> str:
    """Indian financial year (April–March), e.g. 2025-05-10 → '25-26'."""
    first = d.year if d.month >= 4 else d.year - 1
    return f"{first % 100:02d}-{(first + 1) % 100:02d}"
