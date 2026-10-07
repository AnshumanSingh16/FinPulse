"""The engine on the five synthetic entities: the stories, invariants and reproducibility."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from finpulse.analytics import default_as_of
from finpulse.analytics.inputs import FinancialData
from finpulse.early_warning import RULES, detect_warnings, load_config, risk_summary
from finpulse.early_warning.config import SEVERITIES
from finpulse.early_warning.schemas import RiskSummary, WarningsReport
from finpulse.synthetic import SCENARIOS, generate
from tests.analytics.synthetic_adapter import to_financial_data
from tests.analytics.test_engine import truncate

CONFIG = load_config()
CODES = sorted(SCENARIOS)
_data: dict[str, FinancialData] = {}
_summaries: dict[tuple[str, date], RiskSummary] = {}
LEVELS = ("none", *SEVERITIES)


def data(code: str) -> FinancialData:
    if code not in _data:
        _data[code] = to_financial_data(generate(SCENARIOS[code]))
    return _data[code]


def summary(code: str, as_of: date | None = None) -> RiskSummary:
    d = data(code)
    at = as_of or default_as_of(d)
    assert at is not None
    if (code, at) not in _summaries:
        _summaries[(code, at)] = risk_summary(d, at, CONFIG)
    return _summaries[(code, at)]


def warnings(code: str, as_of: date | None = None) -> WarningsReport:
    d = data(code)
    return detect_warnings(d, as_of or default_as_of(d), CONFIG)  # type: ignore[arg-type]


def level_at(s: RiskSummary, at: date) -> str:
    return next(p.level for p in s.timeline if p.as_of == at)


# --- invariants -----------------------------------------------------------------------------------


@pytest.mark.parametrize("code", CODES)
def test_every_warning_is_complete_and_consistent(code: str) -> None:
    report = warnings(code)

    assert {o.rule for o in report.rules} == set(RULES)
    triggered = {o.rule for o in report.rules if o.state == "triggered"}
    assert {w.rule for w in report.warnings} == triggered
    for w in report.warnings:
        assert w.id.startswith("EW-") and len(w.id) == 13
        assert w.title and w.description and w.evidence
        assert w.detected_at == datetime(
            2026, 9, 30, 23, 59, 59, tzinfo=timezone(timedelta(hours=5, minutes=30))
        )
        assert w.first_detected_on <= report.as_of
        t = w.threshold
        crossed = t.observed >= t.value if t.operator == ">=" else t.observed <= t.value
        floor_applied = w.rule == "unusual_transactions"
        assert crossed or floor_applied, w.rule
        # persistent warnings are one step below the tier they reached
        step = SEVERITIES.index(t.tier) - SEVERITIES.index(w.severity)
        assert step == (1 if w.trend == "persistent" else 0) or floor_applied
        if w.current_value is not None and w.previous_value is not None:
            assert w.change == w.current_value - w.previous_value
    order = [(-SEVERITIES.index(w.severity)) for w in report.warnings]
    assert order == sorted(order)


@pytest.mark.parametrize("code", CODES)
def test_summary_agrees_with_the_warnings(code: str) -> None:
    s = summary(code)
    report = warnings(code)

    assert s.counts.total == len(report.warnings) == s.rules_triggered
    assert sum(c.warnings for c in s.categories) == s.counts.total
    assert s.timeline[-1].as_of == s.as_of
    assert (s.timeline[-1].level, s.timeline[-1].index) == (s.risk_level, s.early_warning_index)
    assert [w.id for w in report.warnings][: len(s.top_warnings)] == [w.id for w in s.top_warnings]
    worst = max((SEVERITIES.index(w.severity) for w in report.warnings), default=-1)
    assert LEVELS.index(s.risk_level) >= worst + 1  # never below the worst single warning
    assert len(s.timeline) == 12


@pytest.mark.parametrize("code", CODES)
def test_results_are_deterministic(code: str) -> None:
    d = data(code)
    as_of = default_as_of(d)
    assert as_of is not None

    assert risk_summary(d, as_of, CONFIG) == summary(code)
    assert detect_warnings(d, as_of, CONFIG) == warnings(code)


@pytest.mark.parametrize("code", ["mehra_lighting", "rapid_mobile_hub"])
@pytest.mark.parametrize("as_of", [date(2026, 1, 31), date(2026, 5, 20)])
def test_a_past_run_never_sees_later_data(code: str, as_of: date) -> None:
    d = data(code)

    assert detect_warnings(d, as_of, CONFIG) == detect_warnings(truncate(d, as_of), as_of, CONFIG)
    assert risk_summary(d, as_of, CONFIG) == risk_summary(truncate(d, as_of), as_of, CONFIG)


def test_warning_ids_are_stable_while_the_condition_lasts() -> None:
    aug = {w.rule: w for w in warnings("mehra_lighting", date(2026, 8, 31)).warnings}
    sep = {w.rule: w for w in warnings("mehra_lighting", date(2026, 9, 30)).warnings}

    ongoing = [r for r in sep if r in aug and sep[r].first_detected_on < date(2026, 9, 30)]
    assert ongoing
    for rule in ongoing:
        assert sep[rule].id == aug[rule].id
        assert sep[rule].status in ("ongoing", "escalated", "easing")


# --- the stories -----------------------------------------------------------------------------


def test_mehra_is_flagged_months_before_its_crisis() -> None:
    """Deterioration starts Nov 2025 (ground truth); loan auto-debits bounce from Aug 2026 while
    the credit bureau still shows a clean record."""
    s = summary("mehra_lighting")

    assert s.risk_level == "critical"
    assert s.first_warning_on is not None and s.first_warning_on <= date(2025, 12, 31)
    assert LEVELS.index(level_at(s, date(2025, 12, 31))) >= LEVELS.index("high")
    rules = {w.rule for w in warnings("mehra_lighting").warnings}
    assert {"runway_shrinking", "liquidity_decline", "repayment_slippage"} <= rules
    assert s.trend.direction == "worsening"


def test_mehra_major_customer_loss_names_the_builder() -> None:
    report = warnings("mehra_lighting", date(2026, 3, 31))

    w = next(w for w in report.warnings if w.rule == "major_customer_loss")
    assert "Shree Ganesh Builders" in w.description
    assert w.severity in ("medium", "high")


def test_mehra_receivables_stretch_is_caught_early() -> None:
    rules = {w.rule for w in warnings("mehra_lighting", date(2025, 12, 31)).warnings}

    assert {"receivables_growth", "receivable_days_increase", "expense_acceleration"} <= rules


@pytest.mark.parametrize("code", ["kaveri_packaging", "annapurna_kitchen"])
def test_healthy_businesses_stay_quiet(code: str) -> None:
    s = summary(code)

    assert s.risk_level in ("none", "low")
    assert all(LEVELS.index(p.level) <= LEVELS.index("medium") for p in s.timeline)


def test_freelancer_with_lumpy_income_is_not_alarming_now() -> None:
    s = summary("ananya_rao_design")

    assert s.risk_level in ("low", "medium")
    assert all(w.severity in ("low", "medium") for w in warnings("ananya_rao_design").warnings)


def test_chronic_high_risk_shop_stays_high_all_year() -> None:
    s = summary("rapid_mobile_hub")

    assert s.risk_level in ("high", "critical")
    since_jan = [p for p in s.timeline if p.as_of >= date(2026, 1, 1)]
    assert all(p.level in ("high", "critical") for p in since_jan)
    assert any(w.rule == "liquidity_decline" for w in warnings("rapid_mobile_hub").warnings)


def test_index_is_capped_and_levels_follow_config() -> None:
    s = summary("mehra_lighting", date(2026, 3, 31))

    points = CONFIG.summary.points
    raw = sum(getattr(points, sev) * getattr(s.counts, sev) for sev in SEVERITIES)
    assert s.early_warning_index == min(100, raw)
    assert Decimal(s.early_warning_index) <= 100
