"""The scoring arithmetic, on a two-dimension model where every number is worked by hand."""

from datetime import date
from decimal import Decimal

import pytest

from finpulse.scoring import explain_change, score_passport
from finpulse.scoring.engine import interpolate
from finpulse.scoring.schemas import Passport
from tests.scoring.helpers import NA, report, tiny_model

D = Decimal
CURVE_UP = [(D(0), D(0)), (D(10), D(50)), (D(20), D(100))]
CURVE_DOWN = [(D(0), D(100)), (D(1), D(0))]

BASE = {
    "revenue.volatility": "0.2",  # → 80
    "income.stability": "60",  # → 60          Alpha = (80 + 60) / 2 = 70
    "debt.leverage": "0.5",  # → 50
    "cash.runway": NA,  # → 100 (not burning)   Beta = (50 + 100) / 2 = 75
}  # Health = 0.6 × 70 + 0.4 × 75 = 72


def dims(p: Passport) -> dict[str, Decimal | None]:
    return {d.code: d.score for d in p.dimensions}


@pytest.mark.parametrize(
    ("x", "expected"),
    [(-5, 0), (0, 0), (5, 25), (10, 50), (15, 75), (20, 100), (99, 100)],
)
def test_interpolation_is_piecewise_linear_and_flat_beyond_the_ends(x: int, expected: int) -> None:
    assert interpolate(D(x), CURVE_UP) == D(expected)


def test_interpolation_on_a_decreasing_curve() -> None:
    assert interpolate(D("0.25"), CURVE_DOWN) == D(75)
    assert interpolate(D(2), CURVE_DOWN) == D(0)


def test_scores_are_weighted_means_of_factor_points() -> None:
    p = score_passport(report(BASE), tiny_model())

    assert dims(p) == {"alpha": D("70.0"), "beta": D("75.0")}
    assert p.financial_health.score == D("72.0")
    assert p.financial_health.band is not None and p.financial_health.band.code == "good"
    assert p.financial_health.confidence == D("1.00")
    assert not p.financial_health.provisional


def test_every_point_is_traceable_to_a_factor() -> None:
    p = score_passport(report(BASE), tiny_model())
    contributions = {
        f.metric_code: f.contribution_to_overall for d in p.dimensions for f in d.factors
    }

    # 80×.5×.6, 60×.5×.6, 50×.5×.4, 100×.5×.4
    assert contributions == {
        "revenue.volatility": D("24.0000"),
        "income.stability": D("18.0000"),
        "debt.leverage": D("10.0000"),
        "cash.runway": D("20.0000"),
    }
    assert sum(contributions.values()) == p.financial_health.score


def test_not_applicable_metrics_use_their_configured_points() -> None:
    p = score_passport(report(BASE), tiny_model())
    runway = next(f for d in p.dimensions for f in d.factors if f.metric_code == "cash.runway")

    assert runway.status == "scored_not_applicable" and runway.points == D("100.0")
    assert "Not burning cash" in runway.explanation


def test_missing_factor_shifts_weight_and_lowers_confidence() -> None:
    p = score_passport(report({**BASE, "income.stability": None}), tiny_model())
    alpha = p.dimensions[0]
    stability = alpha.factors[1]

    assert alpha.score == D("80.0")  # volatility now carries the whole dimension
    assert alpha.factors[0].effective_weight == D("1.0000")
    assert stability.status == "excluded" and stability.points is None
    assert stability.contribution_to_overall == 0
    assert alpha.confidence == D("0.50")
    assert p.financial_health.score == D("78.0")  # .6×80 + .4×75
    assert p.financial_health.confidence == D("0.70")


def test_unscored_dimension_drops_out_and_marks_the_passport_provisional() -> None:
    p = score_passport(
        report({**BASE, "revenue.volatility": None, "income.stability": None}), tiny_model()
    )

    assert dims(p)["alpha"] is None
    assert p.financial_health.score == D("75.0")
    assert p.financial_health.confidence == D("0.40")
    assert p.financial_health.provisional


def test_nothing_to_score_gives_no_score_and_no_band() -> None:
    p = score_passport(report({}), tiny_model())

    assert p.financial_health.score is None and p.financial_health.band is None
    assert p.financial_health.confidence == 0


def test_metric_confidence_feeds_dimension_confidence() -> None:
    p = score_passport(report(BASE, {"revenue.volatility": "medium"}), tiny_model())

    assert p.dimensions[0].confidence == D("0.88")  # .5 × .75 + .5 × 1 = .875


def test_not_applicable_without_a_rule_is_excluded() -> None:
    p = score_passport(report({**BASE, "debt.leverage": NA}), tiny_model())
    leverage = p.dimensions[1].factors[0]

    assert leverage.status == "excluded"
    assert p.dimensions[1].score == D("100.0")


def test_band_follows_score_thresholds() -> None:
    poor = score_passport(report({**BASE, "income.stability": "0"}), tiny_model())

    # Alpha (80 + 0) / 2 = 40 → health .6×40 + .4×75 = 54
    assert poor.financial_health.score == D("54.0")
    assert poor.financial_health.band is not None and poor.financial_health.band.code == "poor"


def test_strengths_and_concerns_name_the_metric_and_value() -> None:
    p = score_passport(report({**BASE, "income.stability": "30"}), tiny_model())

    assert [s.metric_code for s in p.strengths] == ["cash.runway", "revenue.volatility"]
    assert [c.metric_code for c in p.concerns] == ["income.stability"]
    assert p.concerns[0].text == "Unstable income (income stability: 30.0/100)."
    assert p.concerns[0].impact == D("-6.00")  # (30 − 50) × .5 × .6


def test_change_is_attributed_to_the_factors_that_moved() -> None:
    before = score_passport(report(BASE, as_of=date(2026, 5, 31)), tiny_model())
    after = score_passport(
        report({**BASE, "debt.leverage": "0.9", "income.stability": "70"}), tiny_model()
    )

    change = explain_change(before, after)

    assert change is not None
    # leverage 50 → 10 points: −40 × .5 × .4 = −8; stability 60 → 70: +10 × .5 × .6 = +3
    assert [(d.metric_code, d.impact) for d in change.drivers] == [
        ("debt.leverage", D("-8.00")),
        ("income.stability", D("3.00")),
    ]
    assert change.delta == D("-5.0") == sum(d.impact for d in change.drivers)
    assert change.from_score == D("72.0") and change.to_score == D("67.0")
    assert change.from_band == "good" and change.to_band == "poor"
    assert "Band moved from Good to Poor" in change.summary
    assert "debt leverage rose (50.0% → 90.0%)" in change.drivers[0].text
    beta = next(d for d in change.dimensions if d.code == "beta")
    assert (beta.from_score, beta.to_score, beta.delta) == (D("75.0"), D("55.0"), D("-20.0"))


def test_no_change_means_no_drivers() -> None:
    p = score_passport(report(BASE), tiny_model())

    change = explain_change(p, p)

    assert change is not None and change.delta == 0 and change.drivers == []
    assert "was unchanged" in change.summary


def test_change_needs_two_scored_passports() -> None:
    scored = score_passport(report(BASE), tiny_model())
    empty = score_passport(report({}), tiny_model())

    assert explain_change(empty, scored) is None


def test_scoring_is_deterministic() -> None:
    assert score_passport(report(BASE), tiny_model()) == score_passport(report(BASE), tiny_model())
