"""Each rule on hand-built histories where the expected numbers can be worked out by hand."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest

from finpulse.analytics import default_as_of
from finpulse.analytics.inputs import FinancialData
from finpulse.analytics.schemas import Period
from finpulse.early_warning import detect_warnings, load_config
from finpulse.early_warning.config import DEFAULT_CONFIG, RuleParams, Tiers, parse_config
from finpulse.early_warning.rules import Finding, Rule, Skip
from finpulse.early_warning.schemas import EarlyWarning, WarningsReport
from finpulse.early_warning.snapshots import History
from tests.analytics.builders import Book
from tests.early_warning.books import trading

CONFIG = load_config()
D = Decimal


def run(data: FinancialData, as_of: date | None = None, config: Any = CONFIG) -> WarningsReport:
    return detect_warnings(data, as_of or default_as_of(data), config)  # type: ignore[arg-type]


def warning(report: WarningsReport, rule: str) -> EarlyWarning:
    found = [w for w in report.warnings if w.rule == rule]
    assert found, f"{rule} not triggered: {[(o.rule, o.state, o.reason) for o in report.rules]}"
    return found[0]


def state(report: WarningsReport, rule: str) -> str:
    return next(o.state for o in report.rules if o.rule == rule)


# --- grading, shared by every rule --------------------------------------------------------------


class Stub(Rule):
    code = "stub"
    category = "cash"
    metric = "cash.balance"
    direction = "above"

    def __init__(self, measure: str, deteriorating: bool, floor: Any = None) -> None:
        self.result = Finding(
            measure=D(measure),
            measure_label="m",
            measure_unit="ratio",
            deteriorating=deteriorating,
            title="t",
            description="d",
            current=None,
            previous=None,
            current_period=Period(start=date.min, end=date.min, label="x"),
            previous_period=None,
            evidence=[],
            severity_floor=floor,
        )

    def evaluate(self, h: History, as_of: date, p: Any) -> Finding | Skip:
        return self.result


PARAMS = RuleParams(enabled=True, tiers=Tiers(low=D(1), medium=D(2), high=D(3)))


@pytest.mark.parametrize(
    ("measure", "deteriorating", "floor", "expected"),
    [
        ("2.5", True, None, ("triggered", "medium")),
        ("2.5", False, None, ("triggered", "low")),  # persistent: one step lower
        ("1.5", False, None, ("clear", None)),  # lowest tier and not worsening
        ("0.5", True, None, ("clear", None)),
        ("0.5", True, "medium", ("triggered", "medium")),  # severity floor (watch-list)
        ("9", True, None, ("triggered", "high")),
    ],
)
def test_grading(measure: str, deteriorating: bool, floor: Any, expected: tuple[str, Any]) -> None:
    outcome = Stub(measure, deteriorating, floor).run(None, date.min, PARAMS)  # type: ignore[arg-type]

    assert (outcome.state, outcome.severity) == expected


def test_disabled_rules_do_not_run() -> None:
    config = parse_config(
        DEFAULT_CONFIG.read_text(encoding="utf-8").replace(
            "[rules.revenue_decline]\n# Revenue in the last 3 complete months vs the 3 before "
            "(ratio; −0.20 = a 20% fall).\nenabled = true",
            "[rules.revenue_decline]\nenabled = false",
        )
    )
    _, data = trading([100_000] * 6 + [70_000] * 3)

    report = run(data, config=config)

    assert state(report, "revenue_decline") == "disabled"
    assert "revenue_decline" not in {w.rule for w in report.warnings}


# --- a steady business -----------------------------------------------------------------------


def test_steady_business_only_flags_its_structural_concentration() -> None:
    _, data = trading([100_000] * 9)

    report = run(data)

    # Alpha Ltd is 60% of sales: the "high" tier, but steady, so reported one step lower.
    [w] = report.warnings
    assert (w.rule, w.severity, w.trend) == ("customer_concentration", "medium", "persistent")
    assert w.threshold.tier == "high" and w.threshold.value == D("0.60")
    assert w.current_value == w.previous_value == D("0.6000")
    assert state(report, "repayment_slippage") == "not_applicable"  # no loans
    assert state(report, "supplier_concentration") == "not_applicable"  # no bills


def test_too_little_history_is_reported_not_guessed() -> None:
    _, data = trading([100_000] * 2)

    report = run(data)

    for rule in (
        "revenue_decline",
        "expense_acceleration",
        "major_customer_loss",
        "revenue_volatility",
        "cash_decline",
        "unusual_transactions",
    ):
        assert state(report, rule) == "insufficient_data", rule


# --- revenue ----------------------------------------------------------------------------------


def test_revenue_decline() -> None:
    _, data = trading([100_000] * 6 + [70_000] * 3)

    w = warning(run(data), "revenue_decline")

    assert w.severity == "high" and w.trend == "deteriorating"
    assert w.current_value == D("70000.00") and w.previous_value == D("100000.00")
    assert w.change == D("-30000.00") and w.change_pct == D("-0.3000")
    t = w.threshold
    assert (t.observed, t.operator, t.value, t.scale) == (D("-0.3000"), "<=", D("-0.30"), D(1))
    assert w.affected_metric.code == "revenue.monthly"
    assert "Revenue fell −30%" in w.description
    assert w.evidence[0].values == {
        "2025-04": D("100000.00"),
        "2025-05": D("100000.00"),
        "2025-06": D("100000.00"),
        "2025-07": D("70000.00"),
        "2025-08": D("70000.00"),
        "2025-09": D("70000.00"),
    }


def test_a_business_wide_fall_is_not_a_customer_loss() -> None:
    _, data = trading([100_000] * 6 + [70_000] * 3)

    assert state(run(data), "major_customer_loss") == "clear"


def test_seasonal_dip_is_downgraded() -> None:
    # Low months in Apr–Jun of both years; the second year's dip is no worse than the first.
    revenue = [100_000.0] * 18
    for i in (3, 4, 5):
        revenue[i] = 65_000
    for i in (15, 16, 17):
        revenue[i] = 70_000
    _, data = trading(revenue)

    w = warning(run(data), "revenue_decline")

    assert w.trend == "persistent" and w.title == "Revenue dip (possibly seasonal)"
    assert "may be seasonal" in w.description
    assert w.threshold.scale > 1  # this business's revenue varies more than the norm
    assert {"same_months_last_year", "normal_volatility"} <= {e.id for e in w.evidence}


# --- receivables ---------------------------------------------------------------------------------


def test_customers_paying_later_raises_receivables_warnings() -> None:
    # From month 7 (Jul 2025) both customers pay 30 days after the due date.
    _, data = trading([100_000] * 10, late_days=lambda month: 0 if month < 6 else 30)

    report = run(data)

    growth = warning(report, "receivables_growth")
    assert growth.current_value == D("200000.00") and growth.previous_value == D("100000.00")
    assert growth.threshold.observed == D("1.0000") and growth.severity == "critical"
    assert "Receivables increased +100%" in growth.description
    assert "Average collection time: 30 → 60 days" in growth.description

    days = warning(report, "receivable_days_increase")
    assert (days.current_value, days.previous_value) == (D("60.0"), D("30.0"))

    late = warning(report, "delayed_collections")
    assert (late.current_value, late.previous_value, late.severity) == (
        D("30.0"),
        D("0.0"),
        "critical",
    )
    assert late.affected_metric.derived


def test_receivables_growing_with_sales_is_only_persistent() -> None:
    # Sales double and receivables double with them: collection is unchanged.
    _, data = trading([100_000] * 7 + [200_000] * 3)

    report = run(data)

    assert state(report, "receivable_days_increase") != "triggered"
    growth = [w for w in report.warnings if w.rule == "receivables_growth"]
    assert not growth or growth[0].trend == "persistent"


# --- debt ------------------------------------------------------------------------------------


def test_bounced_and_late_instalments() -> None:
    book, _ = trading([100_000] * 9)
    lender = book.party("QuickCash Digital", "lender")
    loan = book.loan(lender, 120_000, date(2025, 1, 10), tenor=12)
    for n in range(1, 10):
        due = date(2025, n, 10) + timedelta(days=0)
        late = n >= 8  # Aug and Sep: bounced once, paid 6 days late
        book.instalment(
            loan,
            n,
            due,
            10_000,
            1_200,
            paid=due + timedelta(days=6 if late else 0),
            bounces=1 if late else 0,
        )

    w = warning(run(book.data()), "repayment_slippage")

    assert (w.current_value, w.previous_value, w.severity) == (D(2), D(0), "medium")
    assert w.evidence[0].values == {"count": 2, "bounced": 2, "unpaid": 0}
    assert w.evidence[0].sources[0].table == "loan_installments"


def test_unpaid_instalment_counts_only_once_overdue() -> None:
    book, _ = trading([100_000] * 9)
    lender = book.party("Bank", "lender")
    loan = book.loan(lender, 90_000, date(2025, 1, 10), tenor=9)
    for n in range(1, 10):
        due = date(2025, n, 10)
        book.instalment(loan, n, due, 10_000, 900, paid=due if n < 9 else None)

    w = warning(run(book.data()), "repayment_slippage")

    assert w.current_value == D(1) and w.severity == "low"
    assert w.evidence[0].values["unpaid"] == 1


# --- transactions ------------------------------------------------------------------------------


def test_unusual_payments_and_watch_list() -> None:
    def extra(book: Book) -> list[Any]:
        return [
            (
                date(2025, 9, 12),
                lambda: book.txn(date(2025, 9, 12), -60_000, "expense.maintenance"),
            ),
            (date(2025, 9, 20), lambda: book.txn(date(2025, 9, 20), -100_000, "expense.rent")),
            (date(2025, 9, 21), lambda: book.txn(date(2025, 9, 21), -500, "personal.betting")),
        ]

    _, data = trading([100_000] * 9, extra=extra)

    w = warning(run(data), "unusual_transactions")

    reasons = [e.text for e in w.evidence]
    assert any("first expense.maintenance payment" in r for r in reasons)
    assert any("5.0× the largest expense.rent payment" in r for r in reasons)
    assert any("watch-listed category personal.betting" in r for r in reasons)
    assert w.current_value == D("160500.00") and w.previous_value == D("0.00")
    assert w.severity in ("high", "critical")


def test_a_watch_listed_payment_is_at_least_medium() -> None:
    def extra(book: Book) -> list[Any]:
        return [(date(2025, 9, 21), lambda: book.txn(date(2025, 9, 21), -500, "personal.betting"))]

    _, data = trading([100_000] * 9, extra=extra)

    w = warning(run(data), "unusual_transactions")

    assert w.severity == "medium" and w.threshold.observed < D("0.05")
