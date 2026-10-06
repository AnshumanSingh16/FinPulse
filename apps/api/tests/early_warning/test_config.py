"""The configuration is the methodology: strictly validated, and the only source of thresholds."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from finpulse.early_warning import RULES, load_config
from finpulse.early_warning.config import DEFAULT_CONFIG, Tiers, parse_config

TEXT = DEFAULT_CONFIG.read_text(encoding="utf-8")
D = Decimal


def test_default_config_configures_every_rule() -> None:
    config = load_config()

    assert set(config.rules) == set(RULES)
    assert len(config.sha256) == 64
    assert "not a credit assessment" in config.config.disclaimer


def test_every_requested_signal_has_a_rule() -> None:
    requested = {
        "revenue_decline",
        "expense_acceleration",
        "cash_decline",
        "receivables_growth",
        "receivable_days_increase",
        "delayed_collections",
        "debt_service_burden",
        "new_borrowing",
        "liquidity_decline",
        "runway_shrinking",
        "customer_concentration",
        "supplier_concentration",
        "unusual_transactions",
        "revenue_volatility",
        "cash_flow_volatility",
    }

    assert requested <= set(RULES)


@pytest.mark.parametrize(
    ("tiers", "value", "direction", "expected"),
    [
        ({"low": "1", "medium": "2", "high": "3"}, "0.9", "above", None),
        ({"low": "1", "medium": "2", "high": "3"}, "2", "above", "medium"),
        ({"low": "1", "medium": "2", "high": "3"}, "9", "above", "high"),
        ({"low": "-0.1", "high": "-0.3"}, "-0.2", "below", "low"),
        ({"low": "-0.1", "high": "-0.3"}, "-0.3", "below", "high"),
        ({"low": "-0.1", "high": "-0.3"}, "0", "below", None),
    ],
)
def test_tiers_grade_to_the_highest_crossed(
    tiers: dict[str, str], value: str, direction: str, expected: str | None
) -> None:
    t = Tiers.model_validate(tiers)

    assert t.grade(D(value), direction) == expected  # type: ignore[arg-type]


def replace_once(old: str, new: str) -> str:
    assert TEXT.count(old) == 1, old
    return TEXT.replace(old, new)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        (
            replace_once(
                "tiers = { low = -0.10, medium = -0.20, high = -0.30, critical = -0.45 }",
                "tiers = { low = -0.10, medium = -0.05, high = -0.30, critical = -0.45 }",
            ),
            "rules.revenue_decline: tiers must strictly decrease",
        ),
        (
            replace_once("min_expense_growth = 0.10", "min_expense_growth = 0.10\ncolour = 1"),
            "colour",
        ),
        (replace_once("min_expense_growth = 0.10", ""), "min_expense_growth"),
        (TEXT + "\n[rules.alien_invasion]\nenabled = true\n", "unknown rules in config"),
        (
            TEXT[: TEXT.index("[rules.cash_flow_volatility]")],
            "rules missing from config: ['cash_flow_volatility']",
        ),
        (
            replace_once('watch_severity = "medium"', 'watch_severity = "apocalyptic"'),
            "watch_severity",
        ),
        (
            replace_once(
                "levels = { low = 1, medium = 15, high = 40, critical = 75 }",
                "levels = { low = 1, medium = 50, high = 40, critical = 75 }",
            ),
            "tiers must strictly increase",
        ),
    ],
)
def test_invalid_configs_are_rejected(text: str, message: str) -> None:
    with pytest.raises(ValidationError, match=message.replace("[", r"\[").replace("]", r"\]")):
        parse_config(text)


def test_changing_the_config_changes_the_hash() -> None:
    other = parse_config(replace_once("min_amount = 25000", "min_amount = 30000"))

    assert other.sha256 != load_config().sha256
    assert other.params("unusual_transactions").min_amount == 30000
