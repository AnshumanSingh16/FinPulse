"""Money is stored and computed as integer minor units (paise for INR). Never floats."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

MINOR_PER_MAJOR = 100


def rupees(amount: int | float | str | Decimal) -> int:
    """Convert a major-unit amount to minor units, rounding half up."""
    value = Decimal(str(amount)) * MINOR_PER_MAJOR
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def round_minor(amount: float | Decimal, step_major: int = 1) -> int:
    """Round a (possibly fractional) minor-unit amount to a whole multiple of ``step_major``."""
    step = Decimal(step_major * MINOR_PER_MAJOR)
    value = (Decimal(str(amount)) / step).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return int(value * step)


def format_inr(minor: int) -> str:
    """Indian digit grouping: 1234567.8 → ₹12,34,567.80."""
    sign = "-" if minor < 0 else ""
    major, paise = divmod(abs(minor), MINOR_PER_MAJOR)
    digits = str(major)
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups: list[str] = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join([*groups, tail])
    return f"{sign}₹{digits}.{paise:02d}"
