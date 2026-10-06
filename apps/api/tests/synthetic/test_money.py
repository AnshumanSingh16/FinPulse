import pytest

from finpulse.core.money import format_inr, round_minor, rupees


@pytest.mark.parametrize(
    ("minor", "text"),
    [
        (0, "₹0.00"),
        (99, "₹0.99"),
        (123456789, "₹12,34,567.89"),
        (-5000000, "-₹50,000.00"),
        (100000000000, "₹1,00,00,00,000.00"),
    ],
)
def test_indian_grouping(minor: int, text: str) -> None:
    assert format_inr(minor) == text


def test_conversions_round_half_up() -> None:
    assert rupees("10.005") == 1001
    assert rupees(1_00_000) == 1_00_00_000
    assert round_minor(123_449, step_major=10) == 123_000
    assert round_minor(123_500, step_major=10) == 124_000
