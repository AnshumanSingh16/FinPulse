"""Find the numbers in a piece of text, the way a reader would see them.

Used on both sides of verification: on evidence (to know which numbers exist) and on agent
output (to check each number it states). Dates, identifiers and codes are not numbers here;
Indian digit grouping (₹6,89,747), lakh / crore, percentages, multiples (0.95×) and the Unicode
minus are understood.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

MONTHS = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?"
_STRIP = [
    # identifiers and codes that contain digits: EW-233FAE5A17, revenue_down_20, M:debt.x2
    re.compile(r"[A-Za-z_][\w\-:.]*\d[\w\-:.]*"),
    # ISO dates and months: 2026-09-30, 2026-09
    re.compile(r"\b\d{4}-\d{2}(?:-\d{2})?(?:T[\d:+.]+)?\b"),
    # 30 Sep 2026, 30 September 2026, Sep 2026, Jul–Sep 2026
    re.compile(rf"\b\d{{1,2}}\s+{MONTHS}\s+\d{{4}}\b"),
    re.compile(rf"\b{MONTHS}\s+\d{{4}}\b"),
    re.compile(rf"\b\d{{1,2}}\s+{MONTHS}"),
    # bare years
    re.compile(r"\b(?:19|20)\d{2}\b"),
]
_NUMBER = re.compile(
    r"(?P<neg>[-−–])?\s?(?P<cur>₹|Rs\.?\s?|INR\s?)?"
    r"(?P<num>\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"\s?(?P<suffix>%|×|x\b|lakhs?\b|lacs?\b|crores?\b|cr\b|k\b|points?\b)?",
    re.IGNORECASE,
)
_MULTIPLIER = {
    "lakh": 10**5,
    "lakhs": 10**5,
    "lac": 10**5,
    "lacs": 10**5,
    "crore": 10**7,
    "crores": 10**7,
    "cr": 10**7,
    "k": 10**3,
}


@dataclass(frozen=True)
class Number:
    text: str
    value: Decimal  # absolute value, in plain units (lakh/crore expanded)
    tolerance: Decimal  # half a unit of the displayed precision
    percent: bool
    currency: bool


def strip_non_numbers(text: str) -> str:
    for pattern in _STRIP:
        text = pattern.sub(" ", text)
    return text


def extract(text: str) -> list[Number]:
    out = []
    for m in _NUMBER.finditer(strip_non_numbers(text)):
        raw = m.group("num").replace(",", "")
        try:
            value = Decimal(raw)
        except InvalidOperation:  # pragma: no cover - the pattern only matches digits
            continue
        decimals = len(raw.split(".")[1]) if "." in raw else 0
        suffix = (m.group("suffix") or "").lower()
        multiplier = Decimal(_MULTIPLIER.get(suffix, 1))
        # Precision as displayed: decimals, or trailing zeros of a large whole number (₹6,90,000
        # is rounded to the ten-thousand; 60% and 100 are taken as exact). Half a unit of that
        # precision is the rounding allowed.
        rounded_whole = not decimals and len(raw) >= 4 and suffix != "%" and value != 0
        zeros = len(raw) - len(raw.rstrip("0")) if rounded_whole else 0
        unit = Decimal(10) ** (zeros - decimals)
        out.append(
            Number(
                text=m.group(0).strip(),
                value=value * multiplier,
                tolerance=unit / 2 * multiplier,
                percent=suffix == "%",
                currency=bool(m.group("cur")),
            )
        )
    return out


def numbers_in(value: object) -> set[Decimal]:
    """Every number in an evidence value or text, as absolute values."""
    if value is None or isinstance(value, bool):
        return set()
    if isinstance(value, int | Decimal):
        return {abs(Decimal(value))}
    if isinstance(value, float):
        return {abs(Decimal(str(value)))}
    if isinstance(value, str):
        try:
            return {abs(Decimal(value))}
        except InvalidOperation:
            return {n.value for n in extract(value)}
    if isinstance(value, dict):
        return set().union(*(numbers_in(v) for v in value.values())) if value else set()
    if isinstance(value, list | tuple):
        return set().union(*(numbers_in(v) for v in value)) if value else set()
    return set()


# Small counts and window lengths ("3 months", "12 months", "2 loans") and the 100 in "55/100"
# are allowed without a source: they carry no financial value of their own.
FREE_INTEGERS = frozenset(Decimal(i) for i in (*range(13), 100))


def supported(n: Number, known: set[Decimal]) -> bool:
    if n.value in FREE_INTEGERS and n.tolerance <= Decimal("0.5") and not n.currency:
        return True
    for k in known:
        candidates = (k, k * 100) if n.percent else (k,)
        if any(abs(n.value - c) <= n.tolerance for c in candidates):
            return True
    return False
