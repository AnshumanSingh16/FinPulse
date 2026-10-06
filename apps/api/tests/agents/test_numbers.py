"""Reading numbers the way a reader sees them."""

from decimal import Decimal

import pytest

from finpulse.agents.numbers import extract, numbers_in, supported

D = Decimal


@pytest.mark.parametrize(
    ("text", "values"),
    [
        ("Receivables rose to ₹10,97,992", [D("1097992")]),
        ("a fall of −20%", [D("20")]),
        ("ratio 0.4264, runway 1.7 months", [D("0.4264"), D("1.7")]),
        ("about ₹6.9 lakh", [D("690000.0")]),
        ("₹6,90,000", [D("690000")]),
        ("₹1.2 crore of debt", [D("12000000.0")]),
        ("liquidity 0.95×", [D("0.95")]),
        ("-₹1,77,358 overdrawn", [D("177358")]),
        ("Rs. 5,000 fee", [D("5000")]),
    ],
)
def test_extracts_values(text: str, values: list[Decimal]) -> None:
    assert [n.value for n in extract(text)] == values


@pytest.mark.parametrize(
    "text",
    [
        "since 31 Dec 2025",
        "on 2026-09-30",
        "in Sep 2026",
        "Jul–Sep 2026",
        "warning:EW-233FAE5A17",
        "stress:revenue_down_20",
        "claim RSK-03",
        "in 2026",
    ],
)
def test_dates_ids_and_codes_are_not_numbers(text: str) -> None:
    assert extract(text) == []


def test_numbers_in_evidence_values() -> None:
    assert numbers_in(
        {
            "a": D("0.5919"),
            "b": "689747.00",
            "c": "₹6,89,747 → ₹10,97,992",
            "d": None,
            "e": True,
            "f": [3, "x"],
        }
    ) == {
        D("0.5919"),
        D("689747.00"),
        D("689747"),
        D("1097992"),
        D("3"),
    }


@pytest.mark.parametrize(
    ("claim", "known", "ok"),
    [
        ("59%", {D("0.5919")}, True),  # ratio shown as a rounded percentage
        ("59.2%", {D("0.5919")}, True),
        ("60%", {D("0.5919")}, False),  # not how 0.5919 rounds
        ("₹6,89,747", {D("689747.00")}, True),
        ("₹6.9 lakh", {D("689747.00")}, True),
        ("₹6,90,000", {D("689747.00")}, True),  # rounded to the ten-thousand
        ("₹7,00,000", {D("689747.00")}, True),  # rounded to the lakh
        ("₹6,95,000", {D("689747.00")}, False),  # not a rounding of it
        ("₹6,89,700", {D("689747.00")}, True),
        ("₹6,89,740", {D("689747.00")}, False),
        ("₹4,08,245", {D("1097992"), D("689747")}, False),  # their difference: calculated
        ("48 days", {D("47.8")}, True),
        ("3 months", set(), True),  # small counts need no source
        ("₹3", set(), False),  # but not as money
        ("13 loans", set(), False),
    ],
)
def test_supported(claim: str, known: set[Decimal], ok: bool) -> None:
    [n] = extract(claim)

    assert supported(n, known) is ok
