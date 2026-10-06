"""Sales reach the bank, tax follows sales, and loans are borrowed and repaid in cash."""

from collections import defaultdict
from datetime import date

import pytest

from finpulse.synthetic import SCENARIOS, Dataset
from finpulse.synthetic import calendar as cal
from finpulse.synthetic.bureau import days_past_due
from finpulse.synthetic.categories import Category
from finpulse.synthetic.engine import BOUNCE_CHARGE, MONTH_ABBR
from finpulse.synthetic.loans import amortize, emi
from finpulse.synthetic.summary import monthly_summary


def test_counter_sales_reconcile_to_bank_credits(ds: Dataset) -> None:
    """Takings + money in transit at the start = UPI settlements + cash deposits + money in
    transit at the end. Nothing is created or lost between the till and the bank."""
    takings = sum(s.gross_minor for s in ds.counter_sales)
    till = {Category.SALES_UPI_SETTLEMENT, Category.SALES_CASH_DEPOSIT}
    banked = sum(t.amount_minor for t in ds.transactions if t.category in till)
    opening = ds.opening_cash_on_hand_minor + ds.opening_unsettled_upi_minor
    closing = ds.cash_on_hand_minor + ds.unsettled_upi_minor

    assert opening + takings == banked + closing


def test_counter_sale_register_is_consistent(ds: Dataset) -> None:
    for s in ds.counter_sales:
        assert s.upi_minor + s.cash_minor == s.gross_minor
        assert 0 <= s.tax_minor < s.gross_minor


def test_gst_paid_matches_the_previous_months_net_liability(ds: Dataset) -> None:
    """Each GST payment equals output tax (sales) minus input tax (purchases) for the month it
    is for, whenever no input credit was carried into that month."""
    net: dict[date, int] = defaultdict(int)
    for i in ds.invoices:
        net[cal.month_start(i.issued_on)] += i.tax_minor
    for s in ds.counter_sales:
        net[cal.month_start(s.sold_on)] += s.tax_minor
    for b in ds.bills:
        net[cal.month_start(b.issued_on)] -= b.tax_minor

    payments = [t for t in ds.transactions if t.category == Category.GST]
    if not SCENARIOS[ds.scenario_code].tax.gst_rate:
        assert not payments
        return
    assert payments, "a GST-registered business must pay GST"
    checked = 0
    for tx in payments:
        abbr = tx.description.split()[-1]
        month = cal.month_start(cal.add_months(tx.posted_on, -1))
        while MONTH_ABBR[month.month - 1] != abbr:
            month = cal.add_months(month, -1)
        previous = cal.add_months(month, -1)
        if month <= ds.start_date or previous < ds.start_date or net[previous] < 0:
            continue  # liability depends on warm-up months or on a carried credit
        assert -tx.amount_minor == net[month], (tx.description, month)
        checked += 1
    assert checked >= 6


def test_amortisation_repays_exactly_the_principal() -> None:
    schedule = amortize(1_00_000_00, 0.12, 12)

    assert emi(1_00_000_00, 0.12, 12) == 8_885_00  # ₹8,884.88 rounded to the rupee
    assert sum(i.principal_minor for i in schedule) == 1_00_000_00
    assert schedule[-1].outstanding_after_minor == 0
    assert all(i.amount_minor == i.principal_minor + i.interest_minor for i in schedule)


def test_loans_and_their_schedules_agree(ds: Dataset) -> None:
    for loan in ds.loans:
        schedule = [i for i in ds.installments if i.loan_id == loan.id]
        assert len(schedule) == loan.tenor_months
        assert sum(i.principal_minor for i in schedule) == loan.principal_minor
        assert all(i.amount_minor == i.principal_minor + i.interest_minor for i in schedule)


def test_disbursements_and_repayments_are_bank_transactions(ds: Dataset) -> None:
    txs = {t.id: t for t in ds.transactions}
    lenders = {loan.id: loan.lender_id for loan in ds.loans}
    for loan in ds.loans:
        if loan.disbursed_on >= ds.start_date:
            tx = txs[loan.disbursement_transaction_id]
            assert tx.amount_minor == loan.principal_minor
            assert tx.category == Category.LOAN_DISBURSEMENT and tx.posted_on == loan.disbursed_on
        else:
            assert loan.disbursement_transaction_id is None
    for inst in ds.installments:
        if inst.transaction_id is None:
            assert inst.paid_on is None or inst.paid_on < ds.start_date
            continue
        tx = txs[inst.transaction_id]
        assert tx.amount_minor == -inst.amount_minor
        assert tx.posted_on == inst.paid_on >= inst.due_on
        assert tx.counterparty_id == lenders[inst.loan_id]
        assert tx.category == Category.LOAN_REPAYMENT

    emi_txs = sorted(t.id for t in ds.transactions if t.category == Category.LOAN_REPAYMENT)
    assert emi_txs == sorted(i.transaction_id for i in ds.installments if i.transaction_id)


def test_installment_status_and_bounce_charges(ds: Dataset) -> None:
    for inst in ds.installments:
        if inst.paid_on is None:
            assert inst.status == ("overdue" if inst.due_on <= ds.as_of else "scheduled")
        else:
            assert inst.status == ("paid_on_time" if inst.paid_on <= inst.due_on else "paid_late")
            if inst.bounces:
                assert inst.status == "paid_late"
    charges = [t for t in ds.transactions if t.category == Category.BOUNCE_CHARGE]
    assert all(t.amount_minor == -BOUNCE_CHARGE for t in charges)
    assert len(charges) <= sum(i.bounces for i in ds.installments)


def test_debt_outstanding_reconciles(ds: Dataset) -> None:
    final = monthly_summary(ds)[-1]
    borrowed = sum(loan.principal_minor for loan in ds.loans)
    repaid = sum(
        i.principal_minor
        for i in ds.installments
        if i.paid_on is not None and i.paid_on <= ds.as_of
    )

    assert final.debt_outstanding_minor == borrowed - repaid >= 0


def test_bureau_only_sees_reporting_lenders_and_real_delinquency(ds: Dataset) -> None:
    loans = {loan.id: loan for loan in ds.loans}
    for event in ds.bureau_events:
        assert loans[event.loan_id].reports_to_bureau
        assert event.reported_on > event.event_on
        if event.event_type.startswith("dpd_"):
            schedule = [i for i in ds.installments if i.loan_id == event.loan_id]
            assert days_past_due(schedule, event.event_on) >= int(event.event_type[4:])


def test_monthly_summary_reconciles_with_the_ledger(ds: Dataset) -> None:
    months = monthly_summary(ds)
    (account,) = ds.accounts

    assert sum(m.net_cash_flow_minor for m in months) == (
        months[-1].closing_balance_minor - account.opening_balance_minor
    )
    assert months[-1].closing_balance_minor == ds.transactions[-1].balance_after_minor
    assert sum(m.collections_minor for m in months) == sum(
        p.amount_minor for p in ds.invoice_payments if p.paid_on >= ds.start_date
    )


@pytest.mark.parametrize("code", ["kaveri_packaging", "annapurna_kitchen"])
def test_healthy_businesses_collect_most_of_what_they_invoice(code: str) -> None:
    from tests.synthetic.conftest import dataset_for

    months = monthly_summary(dataset_for(code))
    invoiced = sum(m.invoiced_minor for m in months)
    collected = sum(m.collections_minor for m in months)

    assert 0.9 < collected / invoiced < 1.05
