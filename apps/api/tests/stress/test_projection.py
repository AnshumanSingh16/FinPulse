"""Each shock on a small business with round numbers, so every outcome can be checked by hand.

Baseline (Jul–Sep 2026, every month): customer A pays ₹1,00,000 and customer B ₹50,000 for
invoices issued that month; supplier S is paid ₹40,000 for a bill that month; rent ₹30,000;
salaries ₹20,000; drawings ₹10,000; a loan EMI of ₹6,000 (₹5,000 principal). Net +₹44,000 a
month, so the balance goes from ₹1,00,000 to ₹2,32,000 by 30 Sep. The loan has 9 instalments
left (Oct–Jun) of a 15-month, ₹75,000 loan: ₹45,000 principal at 12%.
"""

from datetime import date
from decimal import Decimal

import pytest

from finpulse.analytics.context import Context
from finpulse.analytics.engine import compute_report
from finpulse.analytics.inputs import FinancialData
from finpulse.core.finance import emi
from finpulse.core.money import round_minor, rupees
from finpulse.scoring import load_model
from finpulse.stress import StressTestRequest, run_stress_test
from finpulse.stress.baseline import build_baseline
from finpulse.stress.projection import Simulation, simulate
from finpulse.stress.schemas import StressTestResult
from finpulse.stress.shocks import SHOCKS, Levers, Shock, ShockParams, register
from tests.analytics.builders import Book

AS_OF = date(2026, 9, 30)
D = Decimal


def business(opening: float = 100_000, overdraft: float = 50_000) -> FinancialData:
    book = Book(opening=opening, overdraft=overdraft)
    a, b = book.party("Customer A"), book.party("Customer B")
    s = book.party("Supplier S", "supplier")
    lender = book.party("Bank", "lender")
    loan = book.loan(lender, 75_000, date(2026, 3, 1), tenor=15)
    for i, m in enumerate((7, 8, 9)):
        book.txn(date(2026, m, 1), -30_000, "expense.rent")
        bill = book.bill(s, date(2026, m, 3), 40_000)
        book.txn(date(2026, m, 5), -6_000, "debt.emi", lender)
        book.pay(bill, date(2026, m, 10), 40_000, s)
        inv_a = book.invoice(a, date(2026, m, 5), 100_000)
        inv_b = book.invoice(b, date(2026, m, 6), 50_000)
        book.receive(inv_a, date(2026, m, 20), 100_000, a)
        book.receive(inv_b, date(2026, m, 25), 50_000, b)
        book.txn(date(2026, m, 26), -20_000, "expense.salary")
        book.txn(date(2026, m, 28), -10_000, "owner.drawings")
        book.instalment(loan, 4 + i, date(2026, m, 5), 5_000, 1_000, paid=date(2026, m, 5))
    for seq in range(1, 4):  # Apr–Jun, paid before the statement
        book.instalment(
            loan, seq, date(2026, 3 + seq, 5), 5_000, 1_000, paid=date(2026, 3 + seq, 5)
        )
    for seq in range(7, 13):  # Oct–Mar remain
        month = 9 + seq - 6
        due = date(2026 + (month - 1) // 12, (month - 1) % 12 + 1, 5)
        book.instalment(loan, seq, due, 5_000, 1_000)
    for seq in range(13, 16):  # Apr–Jun 2027 (beyond a 6-month horizon)
        book.instalment(loan, seq, date(2027, seq - 9, 5), 5_000, 1_000)
    return book.data()


def run(
    shocks: list[dict], data: FinancialData | None = None, horizon: int = 6
) -> StressTestResult:
    request = StressTestRequest.model_validate({"shocks": shocks, "horizon_months": horizon})
    return run_stress_test(data or business(), AS_OF, request, load_model())


def baseline_only(data: FinancialData | None = None) -> Simulation:
    d = data or business()
    b = build_baseline(Context(d, AS_OF), compute_report(d, AS_OF), 6)
    return simulate(Levers(6, b))


def test_baseline_drivers_are_the_monthly_averages() -> None:
    d = business()
    b = build_baseline(Context(d, AS_OF), compute_report(d, AS_OF), 6)

    assert [m.month for m in b.months] == [7, 8, 9]
    assert (b.revenue, b.purchases, b.opex) == (rupees(150_000), rupees(40_000), rupees(50_000))
    assert (b.operating_receipts, b.supplier_payments) == (rupees(150_000), rupees(40_000))
    assert (b.other_outflows, b.other_inflows) == (rupees(10_000), 0)
    assert b.opening_balance == rupees(232_000)
    assert b.scheduled_debt == [rupees(6_000)] * 6
    assert b.debt_outstanding == rupees(45_000)
    assert [c.name for c in b.customers] == ["Customer A", "Customer B"]
    assert b.customers[0].share == D(100_000) / D(150_000)


def test_baseline_projection() -> None:
    sim = baseline_only()

    assert [m.net for m in sim.months] == [rupees(44_000)] * 6
    assert sim.closing_balance == rupees(496_000)  # 2,32,000 + 6 × 44,000
    assert sim.failure is None and sim.runway_months() is None
    assert sim.debt_at_end() == rupees(15_000)  # 45,000 − 6 × 5,000


@pytest.mark.parametrize(
    ("follow", "net", "closing"),
    [(True, 22_000, 364_000), (False, 14_000, 316_000)],  # 120−32−50−10−6 / 120−40−50−10−6
)
def test_revenue_decline(follow: bool, net: int, closing: int) -> None:
    r = run([{"type": "revenue_decline", "decline_pct": "0.2", "costs_follow_revenue": follow}])

    assert r.stressed.revenue == D(720_000)  # 6 × 1,20,000
    assert r.stressed.months[0].net_cash_flow == D(net)
    assert r.stressed.closing_balance == D(closing)
    revenue = next(c for c in r.comparisons if c.key == "revenue")
    assert (revenue.absolute_change, revenue.percentage_change) == (D(-180_000), D("-0.2000"))
    assert revenue.direction == "worse"


def test_revenue_decline_for_part_of_the_horizon() -> None:
    r = run(
        [{"type": "revenue_decline", "decline_pct": "0.5", "start_month": 2, "duration_months": 2}]
    )

    assert [m.revenue for m in r.stressed.months] == [
        D(150_000),
        D(75_000),
        D(75_000),
        D(150_000),
        D(150_000),
        D(150_000),
    ]


def test_operating_expense_increase() -> None:
    r = run([{"type": "operating_expense_increase", "increase_pct": "0.15"}])

    # Opex 50,000 → 57,500: net 36,500 a month
    assert r.stressed.closing_balance == D(232_000 + 6 * 36_500)
    assert r.stressed.expenses == D(6 * (40_000 + 57_500))


def test_supplier_cost_increase_hits_the_largest_supplier() -> None:
    r = run([{"type": "supplier_cost_increase", "increase_pct": "0.10"}])

    assert r.stressed.closing_balance == D(232_000 + 6 * 40_000)  # 4,000 more paid each month
    assert r.stressed.expenses == D(6 * (44_000 + 50_000))
    assert r.scenario.shocks[0].parameters["supplier_id"] is not None
    evidence = next(e for e in r.evidence if e.id == "shock.supplier_cost_increase")
    assert evidence.values["supplier"] == "Supplier S"
    assert evidence.values["extra_per_month"] == D("4000.00")


def test_customer_payment_stop_withholds_then_recovers() -> None:
    r = run([{"type": "customer_payment_stop", "days": 60}])

    daily = D(rupees(100_000)) / (D(365) / 12)
    oct_withheld = round_minor(daily * 31)  # Oct 1–31, whole rupees
    nov_withheld = round_minor(daily * 29)  # Nov 1–29
    withheld = oct_withheld + nov_withheld
    months = r.stressed.months
    assert months[0].net_cash_flow == (D(rupees(44_000) - oct_withheld) / 100).quantize(D("0.01"))
    assert months[2].money_in == (D(rupees(150_000) + withheld) / 100).quantize(D("0.01"))  # Dec
    assert r.stressed.closing_balance == r.baseline.closing_balance  # all recovered
    assert r.stressed.revenue == r.baseline.revenue  # sales continue on credit
    assert r.stressed.minimum_balance_month == "2026-11"
    evidence = next(e for e in r.evidence if e.id == "shock.customer_payment_stop")
    assert evidence.values["customer"] == "Customer A"
    assert evidence.values["withheld"] == (D(withheld) / 100).quantize(D("0.01"))
    assert evidence.values["recovered_in"] == "2026-12-01"


def test_unrecovered_payments_stay_in_receivables() -> None:
    recovered = run([{"type": "customer_payment_stop", "days": 30}])
    lost = run([{"type": "customer_payment_stop", "days": 30, "recovered": False}])

    assert lost.stressed.closing_balance < recovered.stressed.closing_balance
    assert lost.stressed.liquidity_ratio is not None


def test_new_debt() -> None:
    r = run(
        [{"type": "new_debt", "principal": "120000", "annual_rate": "0.12", "tenor_months": 12}]
    )
    payment = emi(rupees(120_000), 0.12, 12)

    assert payment == rupees(10_662)
    # Disbursed in October, five EMIs (Nov–Mar) within the horizon
    assert r.stressed.closing_balance == (
        D(rupees(496_000 + 120_000) - 5 * payment) / 100
    ).quantize(D("0.01"))
    assert r.stressed.months[0].money_in == D(150_000 + 120_000)
    assert r.stressed.months[1].debt_service == D(6_000 + 10_662)


def test_new_debt_default_principal_is_two_months_of_receipts() -> None:
    r = run([{"type": "new_debt"}])

    assert r.scenario.shocks[0].parameters["principal"] == "300000.00"


def test_interest_rate_increase_reprices_remaining_instalments() -> None:
    r = run([{"type": "interest_rate_increase", "increase_bps": 300}])
    new_emi = emi(rupees(45_000), 0.15, 9)  # 9 instalments left, 12% → 15%

    assert r.stressed.months[0].debt_service == (D(new_emi) / 100).quantize(D("0.01"))
    assert r.stressed.closing_balance == (
        D(rupees(232_000) + 6 * (rupees(50_000) - new_emi)) / 100
    ).quantize(D("0.01"))
    assert "12% → 15%" in next(e.text for e in r.evidence if e.id == "shock.interest_rate_increase")


def test_compound_shocks_are_worse_than_either_alone() -> None:
    both = run(
        [
            {"type": "revenue_decline", "decline_pct": "0.2"},
            {"type": "operating_expense_increase", "increase_pct": "0.15"},
        ]
    )
    one = run([{"type": "revenue_decline", "decline_pct": "0.2"}])

    assert both.stressed.closing_balance == one.stressed.closing_balance - D(6 * 7_500)
    assert len(both.scenario.shocks) == 2 and " + " in both.scenario.name


def test_failure_point_when_funds_run_out() -> None:
    book = Book(opening=40_000, overdraft=20_000)
    for m in (7, 8, 9):  # −10,000 a month: balance 10,000 at 30 Sep
        book.txn(date(2026, m, 1), 50_000, "income.client_payment")
        book.txn(date(2026, m, 2), -60_000, "expense.rent")
    request = StressTestRequest.model_validate(
        {"shocks": [{"type": "operating_expense_increase", "increase_pct": "0.01"}]}
    )
    r = run_stress_test(book.data(), AS_OF, request, load_model())

    # Baseline: Oct 0, Nov −10,000, Dec −20,108.33 (₹108.33 overdraft interest) — past the limit.
    base = r.baseline
    assert base.failure_point is not None
    assert base.failure_point.month == "2026-12"
    assert base.failure_point.date == date(2026, 12, 31)  # 10,000 headroom ÷ 10,108.33 a month
    assert base.failure_point.shortfall_at_month_end == D("108.33")
    assert base.risk.level == "critical"
    assert base.cash_runway_months is not None and base.cash_runway_months < 3
    # 1% more rent (600 a month) brings it forward
    assert r.stressed.failure_point is not None
    assert r.stressed.failure_point.date < base.failure_point.date


def test_risk_levels_follow_the_thresholds() -> None:
    assert run([{"type": "revenue_decline", "decline_pct": "0.01"}]).stressed.risk.level == "low"
    # Revenue −60% with costs fixed: −46,000 a month → 88% of the overdraft drawn by March
    high = run([{"type": "revenue_decline", "decline_pct": "0.6", "costs_follow_revenue": False}])
    assert high.stressed.risk.level == "high" and high.stressed.failure_point is None
    # Revenue −80%: −76,000 a month → funds exhausted
    severe = run([{"type": "revenue_decline", "decline_pct": "0.8", "costs_follow_revenue": False}])
    assert severe.stressed.risk.level == "critical"
    assert severe.risk_change.escalated and severe.risk_change.steps == 3


def test_a_new_shock_type_needs_no_engine_changes() -> None:
    class OneOffExpense(Shock):
        code = "test_one_off_expense"
        name = "One-off expense"
        description = "Test only."

        class Params(ShockParams):
            amount: int

        def apply(self, params: ShockParams, levers: Levers) -> None:
            levers.supplier_payments_delta[0] += params.amount  # type: ignore[attr-defined]

    register(OneOffExpense)
    try:
        levers = Levers(6, baseline_only().baseline)
        SHOCKS["test_one_off_expense"].apply(
            OneOffExpense.Params(type="test_one_off_expense", amount=rupees(100_000)), levers
        )
        assert simulate(levers).closing_balance == rupees(396_000)
        with pytest.raises(ValueError, match="registered twice"):
            register(OneOffExpense)
    finally:
        SHOCKS.pop("test_one_off_expense")


def test_start_month_beyond_horizon_is_not_applicable() -> None:
    from finpulse.stress.shocks import ScenarioNotApplicable

    with pytest.raises(ScenarioNotApplicable, match="beyond"):
        run([{"type": "operating_expense_increase", "increase_pct": "0.1", "start_month": 7}])
