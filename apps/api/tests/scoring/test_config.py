"""The scoring configuration is validated strictly."""

import pytest
from pydantic import ValidationError

from finpulse.analytics import CATALOGUE
from finpulse.scoring.config import DEFAULT_MODEL, load_model, parse_model
from tests.scoring.helpers import TINY_MODEL

REQUESTED = {
    "cash_flow_stability": "Cash-Flow Stability",
    "repayment_capacity": "Repayment Capacity",
    "revenue_stability": "Revenue Stability",
    "financial_resilience": "Financial Resilience",
    "debt_health": "Debt Health",
    "transaction_consistency": "Transaction Consistency",
}


def test_default_model_has_the_six_dimensions_and_sound_weights() -> None:
    model = load_model()

    assert {code: d.name for code, d in model.dimensions.items()} == REQUESTED
    assert sum(d.weight for d in model.dimensions.values()) == 1
    for d in model.dimensions.values():
        assert sum(f.weight for f in d.factors) == 1
        assert all(f.metric in CATALOGUE for f in d.factors)
    assert len(model.sha256) == 64


def test_default_model_disclaims_being_a_credit_score() -> None:
    disclaimer = load_model().model.disclaimer.lower()

    assert "not a credit score" in disclaimer
    assert "cibil" in disclaimer and "must not be used for lending" in disclaimer
    assert "not a credit score" in DEFAULT_MODEL.read_text().lower()


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (("weight = 0.6", "weight = 0.7"), "dimension weights must sum to 1"),
        (
            (
                'metric = "income.stability"\nweight = 0.5',
                'metric = "income.stability"\nweight = 0.4',
            ),
            "factor weights must sum to 1",
        ),
        (('"revenue.volatility"', '"revenue.mood"'), "unknown metric"),
        (("[[0, 100], [1, 0]]", "[[1, 100], [0, 0]]"), "strictly increasing"),
        (("[[0, 0], [100, 100]]", "[[0, 0], [100, 120]]"), "less than or equal to 100"),
        (("min_score = 0", "min_score = 10"), "last band must start at 0"),
        (('id = "tiny"', 'id = "tiny"\nsurprise = true'), "Extra inputs are not permitted"),
    ],
)
def test_invalid_configurations_are_rejected(change: tuple[str, str], message: str) -> None:
    old, new = change
    assert old in TINY_MODEL

    with pytest.raises(ValidationError, match=message):
        parse_model(TINY_MODEL.replace(old, new, 1))


def test_config_hash_changes_with_the_file() -> None:
    assert parse_model(TINY_MODEL).sha256 != parse_model(TINY_MODEL + "\n# edit").sha256
