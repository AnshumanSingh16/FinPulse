"""Each metric on a small, hand-checked ledger. Expected values are worked out in the comments."""

from datetime import date
from decimal import Decimal

import pytest

from finpulse.analytics import compute_report
from finpulse.analytics.inputs import FinancialData
from finpulse.analytics.schemas import Metric
from tests.analytics.builders import Book

D = date


def metric(data: FinancialData, code: str, as_of: date) -> Metric:
    report = compute_report(data, as_of)
    (m,) = [m for m in report.metrics if m.code == code]
    return m


def value(data: FinancialData, code: str, as_of: date) -> Decimal | None:
    return metric(data, code, as_of).value


# --- coverage ---------------------------------------------------------------------------------


def test_a_month_counts_only_if_history_starts_in_its_first_week() -> None:
    early, late = Book(), Book()
    early.txn(D(2026, 1, 7), 1, "income.client_payment")
    late.txn(D(2026, 1, 8), 1, "income.client_payment")

    assert compute_report(early.data(), D(2026, 3, 31)).coverage.complete_months == 3
    assert compute_report(late.data(), D(2026, 3, 31)).coverage.complete_months == 2


def test_last_complete_month_respects_a_mid_month_as_of() -> None:
    book = Book()
    book.txn(D(2026, 1, 1), 100, "income.client_payment")
    book.txn(D(2026, 3, 10), 50, "income.client_payment")

    m = metric(book.data(), "cashflow.net_monthly", D(2026, 3, 15))

    assert m.period.label == "2026-02"
    assert m.value == Decimal("0.00")


# --- revenue, expenses, net cash flow ---------------------------------------------------------


def test_revenue_is_invoices_plus_walk_in_sales_excluding_gst() -> None:
    book = Book()
    customer = book.party("A")
    book.txn(D(2026, 1, 2), 100, "income.sales_upi_settlement")
    book.invoice(customer, D(2026, 1, 10), taxable=1000, tax=180)
    book.invoice(customer, D(2026, 2, 1), taxable=500, tax=90)  # next month: excluded
    book.sale(D(2026, 1, 5), gross=118, tax=18)  # 100 net of GST

    m = metric(book.data(), "revenue.monthly", D(2026, 1, 31))

    assert m.value == Decimal("1100.00")
    assert m.components["invoiced_excl_gst"] == Decimal("1000.00")
    assert m.components["walk_in_excl_gst"] == Decimal("100.00")
    assert m.confidence == "high" and m.period.label == "2026-01"
    assert {s.table for s in m.sources} == {"invoices", "counter_sales"}


def test_revenue_falls_back_to_operating_receipts_without_sales_documents() -> None:
    book = Book()
    book.txn(D(2026, 1, 2), 500, "income.client_payment")
    book.txn(D(2026, 1, 20), 300, "income.client_payment")
    book.txn(D(2026, 1, 25), 1000, "debt.loan_disbursement")  # not revenue
    book.txn(D(2026, 1, 26), -200, "expense.rent")

    m = metric(book.data(), "revenue.monthly", D(2026, 1, 31))

    assert m.value == Decimal("800.00")
    assert m.confidence == "low"
    assert m.components["basis"] == "bank_receipts"


def _expense_book(with_bill: bool) -> Book:
    book = Book()
    supplier = book.party("S", "supplier")
    book.txn(D(2026, 1, 2), 10_000, "income.customer_payment")
    if with_bill:
        book.bill(supplier, D(2026, 1, 5), taxable=2000, tax=360)
    for amount, category in [
        (-2360, "expense.supplier"),  # counted via the bill (ex-GST) when bills exist
        (-500, "expense.salary"),  # operating
        (-100, "bank.charges"),  # operating
        (-50, "bank.overdraft_interest"),  # finance cost: excluded
        (-400, "debt.emi"),  # debt service: excluded
        (-300, "owner.drawings"),  # excluded
        (-180, "tax.gst"),  # pass-through tax: excluded
        (-70, None),  # uncategorised: counted (conservative)
        (-1000, "personal.investment"),  # savings: excluded
        (-200, "cash.withdrawal"),  # operating (unclassified cash)
    ]:
        book.txn(D(2026, 1, 6), amount, category)
    return book


def test_expenses_use_supplier_bills_ex_gst_plus_operating_cash_costs() -> None:
    m = metric(_expense_book(with_bill=True).data(), "expenses.monthly", D(2026, 1, 31))

    # 2000 (bill, ex-GST) + 500 + 100 + 70 + 200
    assert m.value == Decimal("2870.00")
    assert m.components["purchases_excl_gst"] == Decimal("2000.00")
    assert m.components["operating_cash_expenses"] == Decimal("870.00")


def test_expenses_use_supplier_payments_when_there_are_no_bills() -> None:
    m = metric(_expense_book(with_bill=False).data(), "expenses.monthly", D(2026, 1, 31))

    assert m.value == Decimal("3230.00")  # 2360 + 870


def test_net_cash_flow_counts_every_transaction() -> None:
    m = metric(_expense_book(with_bill=True).data(), "cashflow.net_monthly", D(2026, 1, 31))

    # 10,000 in − (2360+500+100+50+400+300+180+70+1000+200 = 5160) out
    assert m.value == Decimal("4840.00")
    assert m.components["money_in"] == Decimal("10000.00")
    assert m.components["money_out"] == Decimal("5160.00")


# --- growth & volatility ----------------------------------------------------------------------


def _monthly_invoices(amounts: list[float], start_month: int = 1) -> Book:
    book = Book()
    customer = book.party("A")
    book.txn(D(2026, start_month, 1), 1, "income.customer_payment")
    for i, amount in enumerate(amounts):
        book.invoice(customer, D(2026, start_month + i, 15), taxable=amount)
    return book


def test_revenue_growth_compares_last_three_months_with_the_three_before() -> None:
    data = _monthly_invoices([100_000, 100_000, 100_000, 120_000, 130_000, 140_000]).data()

    m = metric(data, "revenue.growth", D(2026, 6, 30))

    assert m.value == Decimal("0.3000")  # 390,000 / 300,000 − 1
    assert m.components["last_3_months"] == Decimal("390000.00")


def test_growth_needs_six_months() -> None:
    m = metric(_monthly_invoices([1, 2, 3, 4, 5]).data(), "revenue.growth", D(2026, 5, 31))

    assert m.availability == "insufficient_data" and m.value is None and m.confidence is None


def test_revenue_volatility_is_the_coefficient_of_variation() -> None:
    data = _monthly_invoices([100_000, 100_000, 100_000, 120_000, 130_000, 140_000]).data()

    m = metric(data, "revenue.volatility", D(2026, 6, 30))

    # mean 115,000; population sd = sqrt(1,550,000,000/6) ≈ 16,072.8 → CV 0.1398
    assert m.value == Decimal("0.1398")
    assert m.confidence == "high"


def test_volatility_with_four_months_is_medium_confidence() -> None:
    m = metric(_monthly_invoices([50, 150, 50, 150]).data(), "revenue.volatility", D(2026, 4, 30))

    assert m.value == Decimal("0.5000") and m.confidence == "medium"


def test_volatility_needs_four_months() -> None:
    m = metric(_monthly_invoices([1, 2, 3]).data(), "revenue.volatility", D(2026, 3, 31))

    assert m.availability == "insufficient_data"


def test_expense_growth() -> None:
    book = Book()
    supplier = book.party("S", "supplier")
    book.txn(D(2026, 1, 1), 1, "income.customer_payment")
    for i, amount in enumerate([100, 100, 100, 50, 50, 50]):
        book.bill(supplier, D(2026, 1 + i, 10), taxable=amount)

    assert value(book.data(), "expenses.growth", D(2026, 6, 30)) == Decimal("-0.5000")


# --- cash, runway, buffer, liquidity ----------------------------------------------------------


def _burning_book() -> Book:
    """Opening ₹1,00,000, overdraft ₹2,00,000; each month +10,000 in, −60,000 out."""
    book = Book(opening=100_000, overdraft=200_000)
    for month in (1, 2, 3):
        book.txn(D(2026, month, 1), 10_000, "income.client_payment")
        book.txn(D(2026, month, 10), -60_000, "expense.rent")
    return book


def test_cash_balance_is_the_balance_at_the_end_of_as_of() -> None:
    data = _burning_book().data()

    m = metric(data, "cash.balance", D(2026, 3, 31))
    mid = metric(data, "cash.balance", D(2026, 2, 5))

    assert m.value == Decimal("-50000.00")
    assert m.components["overdraft_drawn"] == Decimal("50000.00")
    assert m.components["available_funds"] == Decimal("150000.00")
    # 1,00,000 + 10,000 − 60,000 + 10,000: after the Feb 1 receipt, before Feb 10 rent
    assert mid.value == Decimal("60000.00")


def test_runway_divides_available_funds_by_average_net_burn() -> None:
    m = metric(_burning_book().data(), "cash.runway", D(2026, 3, 31))

    assert m.value == Decimal("3.0")  # 1,50,000 available ÷ 50,000 a month


def test_runway_is_not_applicable_when_not_burning_cash() -> None:
    book = Book(opening=90_000)
    for month in (1, 2, 3):
        book.txn(D(2026, month, 1), 10_000, "income.client_payment")
        book.txn(D(2026, month, 10), -10_000, "expense.rent")

    runway = metric(book.data(), "cash.runway", D(2026, 3, 31))
    buffer = metric(book.data(), "buffer.months", D(2026, 3, 31))

    assert runway.availability == "not_applicable" and runway.value is None
    assert buffer.value == Decimal("9.0")  # 90,000 own cash ÷ 10,000 monthly outflows


def test_buffer_ignores_overdraft_headroom() -> None:
    assert value(_burning_book().data(), "buffer.months", D(2026, 3, 31)) == Decimal("0.0")


def test_liquidity_ratio_and_debt_metrics_share_one_loan_book() -> None:
    book = Book()
    lender = book.party("Bank", "lender")
    loan = book.loan(lender, 12_000, D(2026, 1, 1))
    book.loan(lender, 5_000, D(2026, 4, 15))  # after as_of: ignored
    book.txn(D(2026, 1, 1), 12_000, "debt.loan_disbursement", lender)
    book.txn(D(2026, 1, 5), 7_000, "income.client_payment")
    book.txn(D(2026, 2, 1), -1_100, "debt.emi", lender)
    book.txn(D(2026, 2, 5), 7_000, "income.client_payment")
    book.txn(D(2026, 3, 3), -1_100, "debt.emi", lender)
    book.txn(D(2026, 3, 5), 8_000, "income.client_payment")
    book.instalment(loan, 1, D(2026, 2, 1), 1000, 100, paid=D(2026, 2, 1))
    book.instalment(loan, 2, D(2026, 3, 1), 1000, 100, paid=D(2026, 3, 3), bounces=1)
    book.instalment(loan, 3, D(2026, 4, 1), 1000, 100)
    data, as_of = book.data(), D(2026, 3, 31)

    debt = metric(data, "debt.outstanding", as_of)
    burden = metric(data, "debt.service_burden", as_of)
    payments = metric(data, "payments.consistency", as_of)
    liquidity = metric(data, "liquidity.ratio", as_of)

    assert debt.value == Decimal("10000.00")  # 12,000 − 2 × 1,000 principal repaid
    assert debt.components["loans"] == 1
    assert burden.value == Decimal("0.1000")  # 2,200 due ÷ 22,000 operating receipts
    assert payments.value == Decimal("0.5000")  # 1 of 2 on time (one late, after a bounce)
    assert payments.components["instalments_paid_late"] == 1
    assert payments.confidence == "medium"  # under 6 months of history
    # cash 31,800 ÷ (next 12 months' principal 1,000)
    assert liquidity.value == Decimal("31.8000")


def test_no_loans_means_zero_debt() -> None:
    book = Book()
    book.txn(D(2026, 1, 1), 100, "income.client_payment")

    m = metric(book.data(), "debt.outstanding", D(2026, 1, 31))

    assert m.value == Decimal("0.00") and m.notes == ["No loans on record."]


# --- receivables & payables -------------------------------------------------------------------


def _receivables_book() -> tuple[Book, date]:
    book = Book()
    a = book.party("A")
    supplier = book.party("S", "supplier")
    book.txn(D(2026, 1, 1), 1, "income.sales_upi_settlement")
    inv1 = book.invoice(a, D(2026, 1, 5), 1000)  # due Feb 4
    inv3 = book.invoice(a, D(2026, 2, 1), 300)  # due Mar 3
    book.invoice(a, D(2026, 3, 20), 500)  # due Apr 19, unpaid
    inv4 = book.invoice(a, D(2026, 3, 25), 200)
    paid_bill = book.bill(supplier, D(2026, 2, 1), 500)
    book.bill(supplier, D(2026, 3, 1), 1000)  # unpaid
    book.receive(inv1, D(2026, 2, 10), 400, a)  # partial: 600 left, 55 days late at as_of
    book.pay(paid_bill, D(2026, 2, 20), 500, supplier)
    book.receive(inv3, D(2026, 3, 1), 300, a)
    book.receive(inv4, D(2026, 4, 2), 200, a)  # after as_of: still owed at as_of
    return book, D(2026, 3, 31)


def test_receivables_are_unpaid_balances_with_ageing() -> None:
    book, as_of = _receivables_book()

    m = metric(book.data(), "receivables.outstanding", as_of)

    assert m.value == Decimal("1300.00")  # 600 + 500 + 200
    assert m.components["overdue_31_60_days"] == Decimal("600.00")
    assert m.components["not_yet_due"] == Decimal("700.00")
    assert m.components["overdue_share"] == Decimal("0.4615")
    assert m.components["open_documents"] == 3


def test_receivable_days() -> None:
    book, as_of = _receivables_book()

    m = metric(book.data(), "receivables.days", as_of)

    # Jan 1 – Mar 31 is exactly 90 days; 1,300 owed ÷ 2,000 invoiced × 90
    assert m.value == Decimal("58.5")
    assert m.confidence == "high"


def test_payable_days() -> None:
    book, as_of = _receivables_book()

    assert value(book.data(), "payables.days", as_of) == Decimal("60.0")  # 1,000 ÷ 1,500 × 90


def test_working_capital_metrics_are_not_applicable_without_documents() -> None:
    book = Book()
    book.txn(D(2026, 1, 1), 100, "income.client_payment")
    data = book.data()

    for code in ("receivables.outstanding", "receivables.days", "payables.days"):
        assert metric(data, code, D(2026, 3, 31)).availability == "not_applicable"


# --- concentration ----------------------------------------------------------------------------


def test_customer_concentration_pools_walk_in_sales() -> None:
    book = Book()
    a, b, c = book.party("A"), book.party("B"), book.party("C")
    book.txn(D(2026, 1, 1), 1, "income.customer_payment")
    book.invoice(a, D(2026, 1, 10), 600)
    book.invoice(b, D(2026, 1, 10), 300)
    book.invoice(c, D(2026, 1, 10), 100)
    book.sale(D(2026, 1, 12), 1000)

    m = metric(book.data(), "customers.concentration", D(2026, 6, 30))

    assert m.value == Decimal("0.3000")  # A: 600 of 2,000
    assert m.components["largest"] == "A"
    assert m.components["top_3_share"] == Decimal("0.5000")
    assert m.components["hhi"] == Decimal("0.1150")  # .3² + .15² + .05²
    assert m.components["walk_in_share"] == Decimal("0.5000")


def test_supplier_concentration_from_bills_or_payments() -> None:
    with_bills, payments_only, none = Book(), Book(), Book()
    for book in (with_bills, payments_only, none):
        book.txn(D(2026, 1, 1), 10_000, "income.customer_payment")
    s1, s2 = with_bills.party("S1", "supplier"), with_bills.party("S2", "supplier")
    with_bills.bill(s1, D(2026, 2, 1), 700)
    with_bills.bill(s2, D(2026, 2, 1), 300)
    p1, p2 = payments_only.party("P1", "supplier"), payments_only.party("P2", "supplier")
    payments_only.txn(D(2026, 2, 1), -400, "expense.supplier", p1)
    payments_only.txn(D(2026, 2, 2), -100, "expense.supplier", p2)
    as_of = D(2026, 6, 30)

    billed = metric(with_bills.data(), "suppliers.concentration", as_of)

    assert billed.value == Decimal("0.7000") and billed.components["hhi"] == Decimal("0.5800")
    assert value(payments_only.data(), "suppliers.concentration", as_of) == Decimal("0.8000")
    assert metric(none.data(), "suppliers.concentration", as_of).availability == "not_applicable"


# --- behaviour --------------------------------------------------------------------------------


def test_income_stability_is_100_for_identical_months() -> None:
    book = Book()
    for month in range(1, 7):
        book.txn(D(2026, month, 1), 1000, "income.client_payment")

    assert value(book.data(), "income.stability", D(2026, 6, 30)) == Decimal("100.0")


def test_income_stability_penalises_variation_and_empty_months() -> None:
    book = Book()
    for month in (1, 2, 3, 5, 6):  # nothing in April
        book.txn(D(2026, month, 1), 1000, "income.client_payment")

    m = metric(book.data(), "income.stability", D(2026, 6, 30))

    # CV = √(1/5) ≈ 0.4472 → 100 × (1 − 0.4472) × 5/6 ≈ 46.1
    assert m.value == Decimal("46.1")
    assert m.components["months_with_receipts"] == 5


def test_payment_consistency_with_supplier_bills_and_grace() -> None:
    book = Book()
    s = book.party("S", "supplier")
    book.txn(D(2026, 1, 1), 10_000, "income.customer_payment")
    on_time = book.bill(s, D(2026, 1, 5), 100, terms=10)  # due Jan 15
    within_grace = book.bill(s, D(2026, 1, 6), 100, terms=10)  # due Jan 16
    late = book.bill(s, D(2026, 1, 7), 100, terms=10)  # due Jan 17
    book.bill(s, D(2026, 3, 25), 100, terms=10)  # due Apr 4: not yet assessable
    book.pay(on_time, D(2026, 1, 15), 100, s)
    book.pay(within_grace, D(2026, 1, 21), 100, s)  # 5 days after due: still on time
    book.pay(late, D(2026, 1, 23), 100, s)  # 6 days after due

    m = metric(book.data(), "payments.consistency", D(2026, 3, 31))

    assert m.value == Decimal("0.6667")
    assert m.components["bills_due"] == 3 and m.components["bills_paid_on_time"] == 2


def test_payment_consistency_not_applicable_without_obligations() -> None:
    book = Book()
    book.txn(D(2026, 1, 1), 100, "income.client_payment")

    assert metric(book.data(), "payments.consistency", D(2026, 3, 31)).availability == (
        "not_applicable"
    )


def test_transaction_consistency_weekly_receipts_score_100() -> None:
    book = Book()
    day = D(2025, 12, 30)
    while day <= D(2026, 3, 31):
        book.txn(day, 100, "income.sales_upi_settlement")
        day = D.fromordinal(day.toordinal() + 7)

    m = metric(book.data(), "transactions.consistency", D(2026, 3, 31))

    assert m.value == Decimal("100.0")
    assert m.components["weeks"] == 13 and m.confidence == "high"


def test_transaction_consistency_with_no_receipts_scores_0() -> None:
    book = Book(opening=10_000)
    day = D(2025, 12, 30)
    while day <= D(2026, 3, 31):
        book.txn(day, -10, "expense.rent")
        day = D.fromordinal(day.toordinal() + 7)

    assert value(book.data(), "transactions.consistency", D(2026, 3, 31)) == Decimal("0.0")


def test_transaction_consistency_needs_eight_weeks() -> None:
    book = Book()
    book.txn(D(2026, 3, 1), 100, "income.client_payment")

    m = metric(book.data(), "transactions.consistency", D(2026, 3, 31))

    assert m.availability == "insufficient_data"


@pytest.mark.parametrize("code", ["cash.balance", "liquidity.ratio", "payments.consistency"])
def test_point_in_time_metrics_need_a_transaction(code: str) -> None:
    book = Book()
    book.txn(D(2026, 5, 1), 100, "income.client_payment")

    assert metric(book.data(), code, D(2026, 4, 30)).availability == "insufficient_data"


# --- metrics added for the Financial Passport -------------------------------------------------


def _cash_book() -> Book:
    """Jan net +500; Feb −500; Mar −200 before a ₹5,000 loan."""
    book = Book(opening=10_000)
    book.txn(D(2026, 1, 1), 1000, "income.client_payment")
    book.txn(D(2026, 1, 10), -500, "expense.rent")
    book.txn(D(2026, 2, 1), 1000, "income.client_payment")
    book.txn(D(2026, 2, 10), -1500, "expense.rent")
    book.txn(D(2026, 3, 1), 5000, "debt.loan_disbursement")
    book.txn(D(2026, 3, 2), 1000, "income.client_payment")
    book.txn(D(2026, 3, 10), -1200, "expense.rent")
    return book


def test_cash_positive_months_ignore_borrowing() -> None:
    m = metric(_cash_book().data(), "cashflow.positive_months", D(2026, 3, 31))

    # March is +4,800 with the loan, −200 without it: only January counts.
    assert m.value == Decimal("0.3333")
    assert m.confidence == "medium"  # 3 of the intended 6 months
    assert m.components["borrowed_in_period"] == Decimal("5000.00")


def test_net_cash_margin_excludes_borrowing() -> None:
    m = metric(_cash_book().data(), "cashflow.net_margin", D(2026, 3, 31))

    assert m.value == Decimal("-0.0667")  # (500 − 500 − 200) ÷ 3,000 received


def test_debt_leverage_against_annualised_revenue() -> None:
    book = Book()
    lender, customer = book.party("Bank", "lender"), book.party("A")
    book.loan(lender, 12_000, D(2026, 1, 1))
    book.txn(D(2026, 1, 1), 12_000, "debt.loan_disbursement", lender)
    for month in (1, 2, 3):
        book.invoice(customer, D(2026, month, 10), 1000)

    m = metric(book.data(), "debt.leverage", D(2026, 3, 31))

    assert m.value == Decimal("1.0000")  # 12,000 owed ÷ (3,000 × 4)
    assert m.components["annualised_revenue"] == Decimal("12000.00")


def test_debt_leverage_is_zero_without_loans() -> None:
    book = Book()
    book.txn(D(2026, 1, 1), 100, "income.client_payment")

    assert value(book.data(), "debt.leverage", D(2026, 3, 31)) == Decimal("0.0000")


def test_new_loans_counts_the_last_183_days() -> None:
    book = Book()
    lender = book.party("Bank", "lender")
    book.txn(D(2026, 1, 1), 100, "income.client_payment")
    book.loan(lender, 1000, D(2026, 1, 1))  # 211 days before as_of
    book.loan(lender, 2000, D(2026, 6, 1))
    book.loan(lender, 9000, D(2026, 8, 15))  # after as_of

    m = metric(book.data(), "debt.new_loans_6m", D(2026, 7, 31))

    assert m.value == Decimal("1")
    assert m.components["borrowed"] == Decimal("2000.00")


def test_overdraft_utilisation_is_the_average_share_drawn() -> None:
    book = Book(opening=0, overdraft=1000)
    book.txn(D(2026, 1, 1), -500, "expense.rent")  # 500 drawn every day after

    m = metric(book.data(), "liquidity.overdraft_utilisation", D(2026, 3, 31))

    assert m.value == Decimal("0.5000")
    assert m.components["days_overdrawn"] == 90


def test_overdraft_utilisation_needs_a_facility() -> None:
    book = Book()
    book.txn(D(2026, 1, 1), 100, "income.client_payment")

    m = metric(book.data(), "liquidity.overdraft_utilisation", D(2026, 3, 31))

    assert m.availability == "not_applicable"
