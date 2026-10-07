"""Passports for the synthetic entities: traceable, consistent over time, and telling each
archetype's story."""

from datetime import date
from decimal import Decimal

import pytest

from finpulse.analytics import compute_report, default_as_of
from finpulse.analytics.inputs import FinancialData
from finpulse.scoring import explain_change, load_model, passport_history, score_passport
from finpulse.scoring.history import history_dates, passport_at, with_monthly_change
from finpulse.scoring.schemas import Passport
from finpulse.synthetic import SCENARIOS, generate
from tests.analytics.synthetic_adapter import to_financial_data
from tests.analytics.test_engine import truncate

MODEL = load_model()
_data: dict[str, FinancialData] = {}


def data(code: str) -> FinancialData:
    if code not in _data:
        _data[code] = to_financial_data(generate(SCENARIOS[code]))
    return _data[code]


def passport(code: str, as_of: date | None = None) -> Passport:
    d = data(code)
    return passport_at(d, as_of or default_as_of(d), MODEL)  # type: ignore[arg-type]


def score(p: Passport) -> Decimal:
    assert p.financial_health.score is not None
    return p.financial_health.score


def dim(p: Passport, code: str) -> Decimal:
    value = next(d.score for d in p.dimensions if d.code == code)
    assert value is not None
    return value


codes = pytest.mark.parametrize("code", sorted(SCENARIOS))


@codes
def test_scores_trace_back_to_metrics(code: str) -> None:
    d = data(code)
    as_of = default_as_of(d)
    assert as_of is not None
    report = compute_report(d, as_of)
    p = score_passport(report, MODEL)
    metrics = {m.code: m for m in report.metrics}

    # Rounding bound: the score is shown to 0.1 (±0.05) and each contribution to 0.01 (±0.005).
    total, factors = Decimal(0), 0
    for dimension in p.dimensions:
        assert dimension.score is not None
        factors += len(dimension.factors)
        assert abs(
            sum(f.contribution_to_dimension for f in dimension.factors) - dimension.score
        ) <= Decimal("0.05") + Decimal("0.005") * len(dimension.factors)
        for f in dimension.factors:
            source = metrics[f.metric_code]
            assert (f.metric_value, f.metric_period, f.metric_availability) == (
                source.value,
                source.period,
                source.availability,
            )
            total += f.contribution_to_overall
    assert abs(total - score(p)) <= Decimal("0.05") + Decimal("0.005") * factors
    assert 0 <= score(p) <= 100


@codes
def test_every_passport_carries_the_disclaimer_and_model(code: str) -> None:
    p = passport(code)

    assert "not a credit score" in p.disclaimer.lower()
    assert p.model.version == 1 and p.model.config_sha256 == MODEL.sha256
    assert [d.code for d in p.dimensions] == list(MODEL.dimensions)


def test_healthy_profiles_score_strong() -> None:
    for code in ("kaveri_packaging", "annapurna_kitchen", "ananya_rao_design"):
        p = passport(code)
        assert score(p) >= 80 and p.financial_health.band.code == "strong", code  # type: ignore[union-attr]


def test_thin_file_is_not_penalised_for_having_no_credit_history() -> None:
    p = passport("annapurna_kitchen")

    assert dim(p, "debt_health") == 100 and dim(p, "repayment_capacity") == 100
    assert score(p) >= score(passport("kaveri_packaging"))


def test_mehra_lighting_declines_and_the_passport_says_why() -> None:
    before = passport("mehra_lighting", date(2025, 10, 31))
    after = passport("mehra_lighting")

    assert score(before) - score(after) >= 20
    assert dim(after, "financial_resilience") < 20 and dim(after, "cash_flow_stability") < 35
    concerns = {c.metric_code for c in after.concerns}
    assert {"buffer.months", "cashflow.net_margin"} <= concerns

    change = explain_change(before, after)
    assert change is not None and change.delta < -20
    assert sum(d.impact for d in change.drivers) < -15  # the top drivers explain most of it


def test_high_risk_profile_is_strained_where_it_matters() -> None:
    p = passport("rapid_mobile_hub")

    assert score(p) < 65
    assert dim(p, "financial_resilience") < 30
    assert dim(p, "repayment_capacity") < 65
    assert "payments.consistency" in {c.metric_code for c in p.concerns}


def test_freelancers_weak_spot_is_weekly_regularity() -> None:
    p = passport("ananya_rao_design")

    assert min(d.score for d in p.dimensions if d.score is not None) == dim(
        p, "transaction_consistency"
    )


# --- history and change -----------------------------------------------------------------------


def test_history_dates_are_month_ends_then_as_of() -> None:
    assert history_dates(date(2026, 9, 15), 4, date(2026, 1, 1)) == [
        date(2026, 6, 30),
        date(2026, 7, 31),
        date(2026, 8, 31),
        date(2026, 9, 15),
    ]
    assert history_dates(date(2026, 3, 31), 12, date(2026, 1, 20)) == [
        date(2026, 1, 31),
        date(2026, 2, 28),
        date(2026, 3, 31),
    ]


@codes
def test_history_is_ordered_and_ends_at_the_current_passport(code: str) -> None:
    d = data(code)
    as_of = default_as_of(d)
    assert as_of is not None

    h = passport_history(d, as_of, 6, MODEL)

    assert [p.as_of for p in h.points] == sorted(p.as_of for p in h.points)
    assert len(h.points) == 6 and h.points[-1].as_of == as_of
    assert h.points[-1].score == score(passport(code))
    assert len(h.changes) == 5
    for change, (a, b) in zip(h.changes, zip(h.points, h.points[1:], strict=False), strict=True):
        assert (change.from_as_of, change.to_as_of) == (a.as_of, b.as_of)
        assert change.delta == (b.score - a.score)  # type: ignore[operator]


@pytest.mark.parametrize("code", ["mehra_lighting", "rapid_mobile_hub"])
def test_history_points_never_see_later_data(code: str) -> None:
    d = data(code)
    h = passport_history(d, default_as_of(d), 18, MODEL)  # type: ignore[arg-type]

    for point in h.points[::4]:
        alone = passport_at(truncate(d, point.as_of), point.as_of, MODEL)
        assert alone.financial_health.score == point.score
        assert {x.code: x.score for x in alone.dimensions} == point.dimensions


def test_mehra_history_tells_the_decline() -> None:
    d = data("mehra_lighting")
    h = passport_history(d, default_as_of(d), 18, MODEL)  # type: ignore[arg-type]
    by_month = {p.as_of: p.score for p in h.points}

    assert len(h.points) == 18
    assert by_month[date(2026, 9, 30)] < by_month[date(2025, 10, 31)] - 20  # type: ignore[operator]
    assert h.points[0].provisional and not h.points[-1].provisional  # thin early history
    assert "moved from" in h.summary


def test_current_passport_explains_the_last_month() -> None:
    d = data("mehra_lighting")
    as_of = default_as_of(d)
    assert as_of is not None

    p = with_monthly_change(d, as_of, MODEL)

    assert p.change_from_previous_month is not None
    expected = explain_change(
        passport_at(d, date(2026, 8, 31), MODEL), passport_at(d, as_of, MODEL)
    )
    assert p.change_from_previous_month == expected
    assert p.change_from_previous_month.summary.startswith("Financial health fell")


def test_no_monthly_change_in_the_first_month() -> None:
    d = data("annapurna_kitchen")

    assert with_monthly_change(d, date(2025, 10, 31), MODEL).change_from_previous_month is None
