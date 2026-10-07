"""The demo story, pinned: what the deterministic engines conclude about Sharma Electricals.

Every number the demo shows comes from the engines at request time. These tests make sure the
scenario keeps telling the story the demo script (docs/DEMO.md) describes; if one fails after a
change to the generator, a rule or a scenario, the demo has changed.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from finpulse.analytics import default_as_of
from finpulse.analytics.history import metric_history
from finpulse.early_warning import detect_warnings, load_config, risk_summary
from finpulse.scoring import load_model, with_monthly_change
from finpulse.stress.engine import StressTestRequest, run_stress_test
from finpulse.synthetic import PRIMARY_DEMO, SCENARIOS, generate
from tests.analytics.synthetic_adapter import to_financial_data

DATA = to_financial_data(generate(SCENARIOS[PRIMARY_DEMO]))
AS_OF = default_as_of(DATA)
CONFIG = load_config()


def history(code: str) -> dict[date, Decimal]:
    assert AS_OF is not None
    h = metric_history(DATA, AS_OF, 18, [code])
    return {p.as_of: v for p in h.points if (v := p.values[code]) is not None}


def test_the_demo_entity_and_date() -> None:
    assert PRIMARY_DEMO == "sharma_electricals"
    assert DATA.display_name == "Sharma Electricals"
    assert date(2026, 9, 30) == AS_OF
    # Limited traditional credit history: one bank loan.
    assert len(DATA.loans) == 1


def test_revenue_is_still_growing() -> None:
    revenue = history("revenue.monthly")
    growth = history("revenue.growth")
    assert growth[date(2026, 9, 30)] > 0
    assert revenue[date(2026, 9, 30)] > revenue[date(2025, 9, 30)] * Decimal("1.25")


def test_receivables_and_collection_time_are_rising() -> None:
    receivables = history("receivables.outstanding")
    days = history("receivables.days")
    assert receivables[date(2026, 9, 30)] > 2 * receivables[date(2026, 1, 31)]
    assert days[date(2026, 9, 30)] - days[date(2026, 1, 31)] >= 10


def test_cash_is_declining_and_one_customer_dominates() -> None:
    cash = history("cash.balance")
    concentration = history("customers.concentration")
    assert cash[date(2026, 9, 30)] < Decimal("0.65") * cash[date(2025, 11, 30)]
    assert cash[date(2026, 9, 30)] > 0  # still positive: nothing has gone wrong yet
    assert concentration[date(2026, 9, 30)] >= Decimal("0.35")
    assert concentration[date(2026, 9, 30)] > concentration[date(2026, 3, 31)]


def test_at_first_it_looks_healthy() -> None:
    assert AS_OF is not None
    passport = with_monthly_change(DATA, AS_OF, load_model())
    health = passport.financial_health
    assert health.band is not None and health.band.label == "Sound"
    assert Decimal(70) <= health.score <= Decimal(85)  # type: ignore[operator]
    repayment = next(d for d in passport.dimensions if d.code == "repayment_capacity")
    assert repayment.score is not None and repayment.score > 95


def test_the_early_warning_is_medium_risk_led_by_liquidity_deterioration() -> None:
    assert AS_OF is not None
    summary = risk_summary(DATA, AS_OF, CONFIG)
    report = detect_warnings(DATA, AS_OF, CONFIG)
    assert summary.risk_level == "medium"
    assert report.warnings[0].rule == "liquidity_deterioration"
    assert report.warnings[0].title == "Liquidity deterioration"
    assert {w.severity for w in report.warnings} <= {"low", "medium"}
    assert {"receivables_growth", "customer_concentration"} <= {w.rule for w in report.warnings}


def test_risk_builds_up_rather_than_peaking_earlier() -> None:
    assert AS_OF is not None
    timeline = risk_summary(DATA, AS_OF, CONFIG).timeline
    assert all(p.level in ("none", "low", "medium") for p in timeline)
    assert timeline[-1].index == max(p.index for p in timeline)


def test_a_60_day_delay_by_the_largest_customer_breaks_the_outlook() -> None:
    assert AS_OF is not None
    result = run_stress_test(
        DATA,
        AS_OF,
        StressTestRequest(preset="major_customer_stops_paying_60_days"),
        load_model(),
    )
    assert result.scenario.name == "Largest customer delays payment by 60 days"
    assert (result.risk_change.baseline, result.risk_change.scenario) == ("low", "high")
    assert result.baseline.minimum_balance > 0
    assert result.stressed.minimum_balance < 0  # the account goes overdrawn
