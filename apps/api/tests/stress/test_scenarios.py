"""The ten presets on every synthetic entity: invariants, monotonicity and each entity's story."""

from datetime import date
from decimal import Decimal

import pytest

from finpulse.analytics import default_as_of
from finpulse.analytics.inputs import FinancialData
from finpulse.scoring import load_model
from finpulse.stress import PRESETS, StressTestRequest, run_stress_test
from finpulse.stress.schemas import StressTestResult
from finpulse.stress.shocks import ScenarioNotApplicable
from finpulse.synthetic import SCENARIOS, generate
from tests.analytics.synthetic_adapter import to_financial_data
from tests.analytics.test_engine import truncate

MODEL = load_model()
_data: dict[str, FinancialData] = {}
_runs: dict[tuple[str, str], StressTestResult] = {}

REQUESTED = {
    "revenue_down_10",
    "revenue_down_20",
    "revenue_down_30",
    "major_customer_stops_paying_30_days",
    "major_customer_stops_paying_60_days",
    "major_customer_stops_paying_90_days",
    "operating_expenses_up_15",
    "new_debt",
    "interest_rate_up_300bps",
    "major_supplier_cost_up_10",
}


def data(code: str) -> FinancialData:
    if code not in _data:
        _data[code] = to_financial_data(generate(SCENARIOS[code]))
    return _data[code]


def run(code: str, preset: str) -> StressTestResult:
    if (code, preset) not in _runs:
        d = data(code)
        _runs[(code, preset)] = run_stress_test(
            d,
            default_as_of(d),
            StressTestRequest(preset=preset),
            MODEL,  # type: ignore[arg-type]
        )
    return _runs[(code, preset)]


def applicable(code: str, preset: str) -> bool:
    return not (code == "ananya_rao_design" and preset == "major_supplier_cost_up_10")


CASES = [(c, p) for c in sorted(SCENARIOS) for p in PRESETS if applicable(c, p)]


def test_all_requested_scenarios_exist() -> None:
    assert set(PRESETS) == REQUESTED


@pytest.mark.parametrize(("code", "preset"), CASES)
def test_result_is_internally_consistent(code: str, preset: str) -> None:
    r = run(code, preset)

    for p in (r.baseline, r.stressed):
        assert len(p.months) == r.horizon_months == 6
        balance = p.months[0].closing_balance - p.months[0].net_cash_flow
        for m in p.months:
            assert m.net_cash_flow == m.money_in - m.money_out
            balance += m.net_cash_flow
            assert m.closing_balance == balance
        assert p.closing_balance == p.months[-1].closing_balance
        assert p.revenue == sum(m.revenue for m in p.months)
        assert (p.failure_point is not None) == (p.risk.level == "critical")
    for c in r.comparisons:
        if c.baseline is not None and c.scenario is not None:
            assert c.absolute_change == c.scenario - c.baseline
    impact = r.health_impact
    assert impact.change == impact.scenario_score - impact.baseline_projected_score  # type: ignore[operator]
    assert {e.id for e in r.evidence} >= {"baseline.period", "baseline.cash", "outcome.risk"}
    assert any(e.kind == "shock" for e in r.evidence)
    assert "not a forecast" in r.disclaimer


@pytest.mark.parametrize("code", sorted(SCENARIOS))
def test_baseline_is_the_same_whatever_the_scenario(code: str) -> None:
    baselines = {run(code, p).baseline.model_dump_json() for p in PRESETS if applicable(code, p)}

    assert len(baselines) == 1


@pytest.mark.parametrize("code", sorted(SCENARIOS))
def test_deeper_shocks_hurt_more(code: str) -> None:
    closing = [run(code, f"revenue_down_{n}").stressed.closing_balance for n in (10, 20, 30)]
    lowest = [
        run(code, f"major_customer_stops_paying_{n}_days").stressed.minimum_balance
        for n in (30, 60, 90)
    ]

    assert closing[0] > closing[1] > closing[2]
    assert lowest[0] >= lowest[1] >= lowest[2]
    assert (
        run(code, "revenue_down_30").stressed.closing_balance
        < run(code, "revenue_down_10").baseline.closing_balance
    )


@pytest.mark.parametrize("code", sorted(SCENARIOS))
def test_results_are_deterministic(code: str) -> None:
    d = data(code)
    again = run_stress_test(d, default_as_of(d), StressTestRequest(preset="revenue_down_20"), MODEL)  # type: ignore[arg-type]

    assert again == run(code, "revenue_down_20")


def test_a_past_stress_test_never_sees_later_data() -> None:
    d = data("sharma_electricals")
    as_of = date(2025, 12, 31)
    request = StressTestRequest(preset="major_customer_stops_paying_60_days")

    assert run_stress_test(d, as_of, request, MODEL) == run_stress_test(
        truncate(d, as_of), as_of, request, MODEL
    )


def test_freelancer_has_no_supplier_to_stress() -> None:
    d = data("ananya_rao_design")

    with pytest.raises(ScenarioNotApplicable, match="no suppliers"):
        run_stress_test(
            d, default_as_of(d), StressTestRequest(preset="major_supplier_cost_up_10"), MODEL
        )  # type: ignore[arg-type]


# --- the stories ------------------------------------------------------------------------------


def test_sharma_electricals_is_already_on_the_edge() -> None:
    base = run("sharma_electricals", "revenue_down_10").baseline

    assert base.risk.level == "critical"
    assert base.failure_point is not None and base.failure_point.date < date(2026, 11, 1)
    for preset in ("revenue_down_30", "operating_expenses_up_15", "major_supplier_cost_up_10"):
        stressed = run("sharma_electricals", preset).stressed
        assert stressed.failure_point is not None
        assert stressed.failure_point.date <= base.failure_point.date


def test_sharma_six_months_ago_would_have_survived_a_10pct_fall() -> None:
    d = data("sharma_electricals")
    r = run_stress_test(d, date(2025, 10, 31), StressTestRequest(preset="revenue_down_10"), MODEL)

    assert r.stressed.failure_point is None


def test_new_debt_postpones_failure_but_adds_burden() -> None:
    r = run("sharma_electricals", "new_debt")

    assert r.baseline.failure_point is not None and r.stressed.failure_point is None
    # The loan clears the overdraft, but its EMIs cut repayment capacity and shorten the runway.
    repayment = next(d for d in r.health_impact.dimensions if d.code == "repayment_capacity")
    assert repayment.delta is not None and repayment.delta < 0
    runway = next(c for c in r.comparisons if c.key == "cash_runway_months")
    assert runway.scenario is not None and runway.baseline is not None
    assert runway.scenario < runway.baseline


def test_healthy_business_absorbs_shocks() -> None:
    for preset in PRESETS:
        assert run("kaveri_packaging", preset).stressed.risk.level == "low", preset
    hit = run("kaveri_packaging", "revenue_down_30").health_impact
    assert hit.change is not None and hit.change < -5


def test_high_risk_business_breaks_under_a_revenue_fall() -> None:
    r = run("rapid_mobile_hub", "revenue_down_20")

    assert r.risk_change.baseline == "high" and r.risk_change.scenario == "critical"
    assert r.risk_change.escalated
    assert r.stressed.failure_point is not None
    assert "outcome.failure_point" in {e.id for e in r.evidence}


def test_customer_stop_can_break_liquidity_even_when_recovered() -> None:
    r = run("rapid_mobile_hub", "major_customer_stops_paying_30_days")

    assert r.stressed.failure_point is not None  # a temporary breach…
    gap = r.stressed.closing_balance - r.baseline.closing_balance
    assert abs(gap) < Decimal(5_000)  # …though the money comes back (gap = overdraft interest)


def test_rate_rise_without_debt_changes_nothing_material() -> None:
    r = run("annapurna_kitchen", "interest_rate_up_300bps")

    assert r.stressed.closing_balance == r.baseline.closing_balance
    assert r.health_impact.change == 0
