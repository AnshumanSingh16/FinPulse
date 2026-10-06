"""Month-by-month roll-up of a dataset: sales, cash, receivables, payables, debt.

This is bookkeeping, not analytics: it restates what the dataset contains so a person (or a
test) can check that the pieces reconcile. The financial-health metrics FinPulse computes live in
the analytics layer and are built later.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from finpulse.synthetic import calendar as cal
from finpulse.synthetic.categories import Category
from finpulse.synthetic.model import Dataset

DEBT_SERVICE = {Category.LOAN_REPAYMENT}


@dataclass(frozen=True, slots=True)
class MonthSummary:
    month: date
    invoiced_minor: int  # sales invoices issued (incl. tax)
    counter_sales_minor: int  # walk-in takings (incl. tax)
    collections_minor: int  # receipts allocated to invoices
    purchases_minor: int  # supplier bills received (incl. tax)
    supplier_payments_minor: int
    credits_minor: int  # all money into the bank
    debits_minor: int  # all money out of the bank (positive number)
    closing_balance_minor: int
    min_balance_minor: int
    receivables_minor: int  # unpaid invoice balances at month end
    payables_minor: int  # unpaid bill balances at month end
    debt_outstanding_minor: int  # loan principal outstanding at month end
    emi_paid_minor: int
    emi_bounces: int

    @property
    def net_cash_flow_minor(self) -> int:
        return self.credits_minor - self.debits_minor


def outstanding(
    totals: dict[uuid.UUID, tuple[date, int]],
    payments: list[tuple[uuid.UUID, date, int]],
    on: date,
) -> int:
    """Unpaid balance across documents issued by ``on``, counting payments made by ``on``."""
    issued = sum(total for issued_on, total in totals.values() if issued_on <= on)
    paid = sum(amount for doc, paid_on, amount in payments if paid_on <= on and doc in totals)
    return issued - paid


def monthly_summary(ds: Dataset) -> list[MonthSummary]:
    invoice_totals = {i.id: (i.issued_on, i.total_minor) for i in ds.invoices}
    invoice_paid = [(p.document_id, p.paid_on, p.amount_minor) for p in ds.invoice_payments]
    bill_totals = {b.id: (b.issued_on, b.total_minor) for b in ds.bills}
    bill_paid = [(p.document_id, p.paid_on, p.amount_minor) for p in ds.bill_payments]
    opening = sum(a.opening_balance_minor for a in ds.accounts)

    months: list[MonthSummary] = []
    balance = opening
    first = ds.start_date
    while first <= ds.as_of:
        last = min(cal.month_end(first), ds.as_of)

        def within(d: date, first: date = first, last: date = last) -> bool:
            return first <= d <= last

        txs = [t for t in ds.transactions if within(t.posted_on)]
        min_balance = balance
        for t in txs:
            min_balance = min(min_balance, t.balance_after_minor)
        if txs:
            balance = txs[-1].balance_after_minor

        principal = sum(
            loan.principal_minor for loan in ds.loans if loan.disbursed_on <= last
        ) - sum(
            i.principal_minor
            for i in ds.installments
            if i.paid_on is not None and i.paid_on <= last
        )
        months.append(
            MonthSummary(
                month=first,
                invoiced_minor=sum(i.total_minor for i in ds.invoices if within(i.issued_on)),
                counter_sales_minor=sum(
                    s.gross_minor for s in ds.counter_sales if within(s.sold_on)
                ),
                collections_minor=sum(
                    p.amount_minor for p in ds.invoice_payments if within(p.paid_on)
                ),
                purchases_minor=sum(b.total_minor for b in ds.bills if within(b.issued_on)),
                supplier_payments_minor=sum(
                    p.amount_minor for p in ds.bill_payments if within(p.paid_on)
                ),
                credits_minor=sum(t.amount_minor for t in txs if t.amount_minor > 0),
                debits_minor=-sum(t.amount_minor for t in txs if t.amount_minor < 0),
                closing_balance_minor=balance,
                min_balance_minor=min_balance,
                receivables_minor=outstanding(invoice_totals, invoice_paid, last),
                payables_minor=outstanding(bill_totals, bill_paid, last),
                debt_outstanding_minor=principal,
                emi_paid_minor=-sum(t.amount_minor for t in txs if t.category in DEBT_SERVICE),
                emi_bounces=sum(1 for t in txs if t.category == Category.BOUNCE_CHARGE),
            )
        )
        first = cal.add_months(first, 1)
    return months
