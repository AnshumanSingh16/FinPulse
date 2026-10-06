"""Invoices drive receivables, bills drive payables, and every settlement is real money."""

from datetime import date

import pytest

from finpulse.synthetic import Dataset
from finpulse.synthetic.categories import Category
from finpulse.synthetic.model import Bill, Invoice, Settlement

INCOME = {Category.CUSTOMER_PAYMENT, Category.PLATFORM_PAYOUT, Category.CLIENT_PAYMENT}


def expected_status(doc: Invoice | Bill, paid: int, as_of: date) -> str:
    if paid >= doc.total_minor:
        return "paid"
    if doc.due_on < as_of:
        return "overdue"
    return "partially_paid" if paid else "open"


def paid_by(payments: list[Settlement], doc_id: object, on: date) -> int:
    return sum(p.amount_minor for p in payments if p.document_id == doc_id and p.paid_on <= on)


@pytest.mark.parametrize("kind", ["invoices", "bills"])
def test_document_amounts_add_up(ds: Dataset, kind: str) -> None:
    for doc in getattr(ds, kind):
        assert doc.taxable_minor + doc.tax_minor == doc.total_minor
        assert doc.total_minor > 0 and doc.tax_minor >= 0
        assert doc.due_on >= doc.issued_on


@pytest.mark.parametrize(
    ("docs", "payments"), [("invoices", "invoice_payments"), ("bills", "bill_payments")]
)
def test_settlements_never_exceed_the_document_and_status_agrees(
    ds: Dataset, docs: str, payments: str
) -> None:
    settled = list(getattr(ds, payments))
    for doc in getattr(ds, docs):
        paid = paid_by(settled, doc.id, ds.as_of)
        assert 0 <= paid <= doc.total_minor
        assert doc.status == expected_status(doc, paid, ds.as_of)


def test_each_invoice_payment_is_a_matching_bank_credit(ds: Dataset) -> None:
    txs = {t.id: t for t in ds.transactions}
    invoices = {i.id: i for i in ds.invoices}
    for p in ds.invoice_payments:
        if p.transaction_id is None:  # paid before the history window
            assert p.paid_on < ds.start_date
            continue
        tx = txs[p.transaction_id]
        assert tx.amount_minor == p.amount_minor > 0
        assert tx.posted_on == p.paid_on
        assert tx.counterparty_id == invoices[p.document_id].customer_id
        assert tx.category in INCOME


def test_each_bill_payment_is_a_matching_bank_debit(ds: Dataset) -> None:
    txs = {t.id: t for t in ds.transactions}
    bills = {b.id: b for b in ds.bills}
    for p in ds.bill_payments:
        if p.transaction_id is None:
            assert p.paid_on < ds.start_date
            continue
        tx = txs[p.transaction_id]
        assert tx.amount_minor == -p.amount_minor < 0
        assert tx.posted_on == p.paid_on
        assert tx.counterparty_id == bills[p.document_id].supplier_id
        assert tx.category == Category.SUPPLIER_PAYMENT


def test_every_customer_receipt_and_supplier_payment_is_allocated_exactly_once(
    ds: Dataset,
) -> None:
    receipts = [t.id for t in ds.transactions if t.category in INCOME]
    supplier = [t.id for t in ds.transactions if t.category == Category.SUPPLIER_PAYMENT]

    assert sorted(receipts) == sorted(
        p.transaction_id for p in ds.invoice_payments if p.transaction_id
    )
    assert sorted(supplier) == sorted(
        p.transaction_id for p in ds.bill_payments if p.transaction_id
    )


@pytest.mark.parametrize(
    ("docs", "payments"), [("invoices", "invoice_payments"), ("bills", "bill_payments")]
)
def test_balances_roll_forward(ds: Dataset, docs: str, payments: str) -> None:
    """closing = opening + issued in window − settled in window."""
    documents, settled = list(getattr(ds, docs)), list(getattr(ds, payments))
    before = ds.start_date

    opening = sum(
        d.total_minor
        - sum(p.amount_minor for p in settled if p.document_id == d.id and p.paid_on < before)
        for d in documents
        if d.issued_on < before
    )
    issued = sum(d.total_minor for d in documents if d.issued_on >= before)
    collected = sum(p.amount_minor for p in settled if before <= p.paid_on <= ds.as_of)
    closing = sum(d.total_minor - paid_by(settled, d.id, ds.as_of) for d in documents)

    assert closing == opening + issued - collected
    assert closing >= 0


def test_documents_from_before_the_window_were_still_open_at_its_start(ds: Dataset) -> None:
    for docs, settled in ((ds.invoices, ds.invoice_payments), (ds.bills, ds.bill_payments)):
        for doc in docs:
            if doc.issued_on < ds.start_date:
                early = sum(
                    p.amount_minor
                    for p in settled
                    if p.document_id == doc.id and p.paid_on < ds.start_date
                )
                assert early < doc.total_minor
