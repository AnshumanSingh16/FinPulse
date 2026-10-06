"""Shared, pre-computed facts about one entity as of one date.

Every metric reads from a ``Context`` rather than re-scanning raw records, so the month
boundaries, the balance lookup and the receivable arithmetic are defined exactly once.
"""

from __future__ import annotations

import bisect
from collections import defaultdict
from collections.abc import Iterable
from datetime import date, timedelta

from finpulse.analytics import classify
from finpulse.analytics.inputs import Document, FinancialData, Payment, Txn
from finpulse.analytics.schemas import Period
from finpulse.core.dates import add_months, month_end, month_start

# A month counts as covered if the history starts within its first week (bank statements
# rarely begin with a transaction on the 1st).
COVERAGE_GRACE_DAYS = 7


def last_complete_month(as_of: date) -> date:
    """First day of the latest calendar month that has fully ended by ``as_of``."""
    if as_of == month_end(as_of):
        return month_start(as_of)
    return add_months(month_start(as_of), -1)


def month_label(m: date) -> str:
    return m.strftime("%Y-%m")


class Context:
    def __init__(self, data: FinancialData, as_of: date) -> None:
        self.data = data
        self.as_of = as_of
        self.txns: list[Txn] = [t for t in data.transactions if t.posted_on <= as_of]
        self.first_date: date | None = self.txns[0].posted_on if self.txns else None
        self.parties = {p.id: p for p in data.counterparties}
        self.invoices = [d for d in data.invoices if d.issued_on <= as_of]
        self.bills = [d for d in data.bills if d.issued_on <= as_of]
        self.invoice_payments = [p for p in data.invoice_payments if p.paid_on <= as_of]
        self.bill_payments = [p for p in data.bill_payments if p.paid_on <= as_of]
        self.counter_sales = [s for s in data.counter_sales if s.sold_on <= as_of]
        self.loans = [loan for loan in data.loans if loan.disbursed_on <= as_of]
        loan_ids = {loan.id for loan in self.loans}
        self.installments = [i for i in data.installments if i.loan_id in loan_ids]
        # Decided from data on or before as_of only, so a past report never depends on the future.
        self.has_sales_documents = bool(self.invoices or self.counter_sales)
        self.has_bills = bool(self.bills)

        self.months = self._covered_months()
        self._index_balances()
        self._aggregate_months()

    # --- coverage --------------------------------------------------------------------------

    def _covered_months(self) -> list[date]:
        if self.first_date is None:
            return []
        first = month_start(self.first_date)
        if self.first_date.day > COVERAGE_GRACE_DAYS:
            first = add_months(first, 1)
        last = last_complete_month(self.as_of)
        months = []
        while first <= last:
            months.append(first)
            first = add_months(first, 1)
        return months

    def window(self, n: int) -> list[date]:
        """The last ``n`` covered complete months (fewer if the history is shorter)."""
        return self.months[-n:] if n else []

    @staticmethod
    def months_period(months: list[date], label: str) -> Period:
        return Period(start=months[0], end=month_end(months[-1]), label=label)

    def as_of_period(self) -> Period:
        return Period(start=self.as_of, end=self.as_of, label="as_of")

    def days_period(self, days: int) -> Period:
        start = self.as_of - timedelta(days=days - 1)
        return Period(start=start, end=self.as_of, label=f"trailing_{days}_days")

    def covered_days(self, days: int) -> int:
        """How many of the last ``days`` days the history actually covers."""
        if self.first_date is None:
            return 0
        return max(0, min(days, (self.as_of - self.first_date).days + 1))

    # --- balances --------------------------------------------------------------------------

    def _index_balances(self) -> None:
        self._balances: dict[object, tuple[list[date], list[int]]] = {}
        for account in self.data.accounts:
            rows = [t for t in self.txns if t.account_id == account.id]
            self._balances[account.id] = (
                [t.posted_on for t in rows],
                [t.balance_after_minor for t in rows],
            )

    def balance_at(self, day: date) -> int:
        """Total end-of-day balance across accounts (negative = overdrawn)."""
        total = 0
        for account in self.data.accounts:
            dates, balances = self._balances[account.id]
            i = bisect.bisect_right(dates, day)
            total += balances[i - 1] if i else account.opening_balance_minor
        return total

    @property
    def overdraft_limit(self) -> int:
        return sum(a.overdraft_limit_minor for a in self.data.accounts)

    # --- documents -------------------------------------------------------------------------

    @staticmethod
    def open_balance(doc: Document, payments: Iterable[Payment], on: date) -> int:
        return doc.total_minor - sum(
            p.amount_minor for p in payments if p.document_id == doc.id and p.paid_on <= on
        )

    def _paid_by_document(self, payments: list[Payment]) -> dict[object, list[Payment]]:
        grouped: dict[object, list[Payment]] = defaultdict(list)
        for p in payments:
            grouped[p.document_id].append(p)
        return grouped

    def open_documents(
        self, docs: list[Document], payments: list[Payment], on: date
    ) -> list[tuple[Document, int]]:
        by_doc = self._paid_by_document(payments)
        out = []
        for doc in docs:
            if doc.issued_on > on:
                continue
            balance = self.open_balance(doc, by_doc.get(doc.id, []), on)
            if balance > 0:
                out.append((doc, balance))
        return out

    def receivables_at(self, on: date) -> int:
        return sum(b for _, b in self.open_documents(self.invoices, self.invoice_payments, on))

    def payables_at(self, on: date) -> int:
        return sum(b for _, b in self.open_documents(self.bills, self.bill_payments, on))

    # --- monthly aggregates ----------------------------------------------------------------

    def _aggregate_months(self) -> None:
        self.invoiced_taxable: dict[date, int] = defaultdict(int)
        self.counter_taxable: dict[date, int] = defaultdict(int)
        self.purchases_taxable: dict[date, int] = defaultdict(int)
        self.opex_cash: dict[date, int] = defaultdict(int)
        self.credits: dict[date, int] = defaultdict(int)
        self.debits: dict[date, int] = defaultdict(int)
        self.operating_inflows: dict[date, int] = defaultdict(int)
        self.debt_service_paid: dict[date, int] = defaultdict(int)

        for inv in self.invoices:
            self.invoiced_taxable[month_start(inv.issued_on)] += inv.taxable_minor
        for sale in self.counter_sales:
            self.counter_taxable[month_start(sale.sold_on)] += sale.gross_minor - sale.tax_minor
        for bill in self.bills:
            self.purchases_taxable[month_start(bill.issued_on)] += bill.taxable_minor
        for t in self.txns:
            m = month_start(t.posted_on)
            if t.amount_minor > 0:
                self.credits[m] += t.amount_minor
                if classify.is_operating_inflow(t.category):
                    self.operating_inflows[m] += t.amount_minor
            else:
                self.debits[m] += -t.amount_minor
                if classify.is_operating_expense(
                    t.category, include_supplier_payments=not self.has_bills
                ):
                    self.opex_cash[m] += -t.amount_minor
                if t.category == classify.DEBT_SERVICE:
                    self.debt_service_paid[m] += -t.amount_minor

    def revenue(self, m: date) -> int:
        """Sales excluding GST: invoices issued + walk-in sales in the month. Without any sales
        documents, falls back to operating cash receipts (see ``revenue_basis``)."""
        if not self.has_sales_documents:
            return self.operating_inflows[m]
        return self.invoiced_taxable[m] + self.counter_taxable[m]

    @property
    def revenue_basis(self) -> str:
        return "sales_documents" if self.has_sales_documents else "bank_receipts"

    def expenses(self, m: date) -> int:
        """Operating costs excluding GST: purchases billed in the month (ex-tax) plus other
        operating cash expenses. Without supplier bills, supplier payments are used instead."""
        return self.purchases_taxable[m] + self.opex_cash[m]

    def net_cash_flow(self, m: date) -> int:
        return self.credits[m] - self.debits[m]

    def txns_in(self, months: list[date]) -> list[Txn]:
        if not months:
            return []
        start, end = months[0], month_end(months[-1])
        return [t for t in self.txns if start <= t.posted_on <= end]
