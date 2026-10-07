"""Liquidity deterioration: cash draining into unpaid invoices, which the liquidity ratio hides."""

from __future__ import annotations

from datetime import date

from finpulse.analytics import default_as_of
from finpulse.early_warning import detect_warnings, load_config, risk_summary
from finpulse.synthetic import SCENARIOS, generate
from tests.analytics.synthetic_adapter import to_financial_data

CONFIG = load_config()


def report(code: str, as_of: date | None = None):  # type: ignore[no-untyped-def]
    data = to_financial_data(generate(SCENARIOS[code]))
    return detect_warnings(data, as_of or default_as_of(data), CONFIG)  # type: ignore[arg-type]


def outcome(code: str, as_of: date | None = None):  # type: ignore[no-untyped-def]
    return next(r for r in report(code, as_of).rules if r.rule == "liquidity_deterioration")


def test_it_catches_growth_draining_cash() -> None:
    (w,) = [w for w in report("sharma_electricals").warnings if w.rule == "liquidity_deterioration"]
    assert w.severity == "medium" and w.category == "liquidity"
    assert w.title == "Liquidity deterioration"
    # It says what the liquidity ratio does not show.
    assert "counts receivables as liquid" in w.description
    assert {e.id for e in w.evidence} >= {"receivables_now", "cash_average", "collection_days"}


def test_healthy_businesses_never_trip_it() -> None:
    for code in ("kaveri_packaging", "annapurna_kitchen"):
        data = to_financial_data(generate(SCENARIOS[code]))
        as_of = default_as_of(data)
        assert as_of is not None
        timeline = risk_summary(data, as_of, CONFIG).timeline
        assert not any("liquidity_deterioration" in p.rules for p in timeline), code


def test_invoices_not_yet_due_are_not_a_liquidity_problem() -> None:
    # Kaveri's receivables jump in April 2026 with a batch of invoices that are mostly not due.
    result = outcome("kaveri_packaging", date(2026, 4, 30))
    assert result.state == "clear"
    assert result.reason is not None and "overdue" in result.reason


def test_it_stays_clear_when_cash_is_not_falling() -> None:
    result = outcome("annapurna_kitchen")
    assert result.state in ("clear", "insufficient_data")
