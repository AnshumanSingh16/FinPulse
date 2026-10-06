"""A tiny bookkeeping builder for hand-checkable analytics fixtures. Amounts are in rupees."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta

from finpulse.analytics.inputs import (
    Account,
    CounterSale,
    Document,
    FinancialData,
    Installment,
    Loan,
    Party,
    Payment,
    Txn,
)

ACCOUNT = uuid.UUID(int=1)


def rs(rupees: float) -> int:
    return round(rupees * 100)


@dataclass
class Book:
    opening: float = 0
    overdraft: float = 0
    kind: str = "business"
    data_through: date | None = None
    _ids: int = 100
    txns: list[Txn] = field(default_factory=list)
    parties: list[Party] = field(default_factory=list)
    invoices: list[Document] = field(default_factory=list)
    invoice_payments: list[Payment] = field(default_factory=list)
    bills: list[Document] = field(default_factory=list)
    bill_payments: list[Payment] = field(default_factory=list)
    loans: list[Loan] = field(default_factory=list)
    installments: list[Installment] = field(default_factory=list)
    counter_sales: list[CounterSale] = field(default_factory=list)

    def _id(self) -> uuid.UUID:
        self._ids += 1
        return uuid.UUID(int=self._ids)

    def party(self, name: str, kind: str = "customer") -> Party:
        p = Party(self._id(), name, kind)
        self.parties.append(p)
        return p

    def txn(
        self, day: date, rupees: float, category: str | None, party: Party | None = None
    ) -> Txn:
        balance = self.txns[-1].balance_after_minor if self.txns else rs(self.opening)
        t = Txn(
            id=self._id(),
            account_id=ACCOUNT,
            posted_on=day,
            seq=len(self.txns) + 1,
            amount_minor=rs(rupees),
            balance_after_minor=balance + rs(rupees),
            category=category,
            counterparty_id=party.id if party else None,
        )
        if self.txns and day < self.txns[-1].posted_on:
            raise ValueError("post transactions in date order")
        self.txns.append(t)
        return t

    def invoice(
        self, customer: Party, issued: date, taxable: float, tax: float = 0, terms: int = 30
    ) -> Document:
        doc = Document(
            self._id(),
            customer.id,
            issued,
            issued + timedelta(days=terms),
            rs(taxable),
            rs(tax),
            rs(taxable + tax),
        )
        self.invoices.append(doc)
        return doc

    def receive(self, doc: Document, day: date, rupees: float, party: Party) -> None:
        t = self.txn(day, rupees, "income.customer_payment", party)
        self.invoice_payments.append(Payment(self._id(), doc.id, t.id, day, rs(rupees)))

    def bill(
        self, supplier: Party, issued: date, taxable: float, tax: float = 0, terms: int = 30
    ) -> Document:
        doc = Document(
            self._id(),
            supplier.id,
            issued,
            issued + timedelta(days=terms),
            rs(taxable),
            rs(tax),
            rs(taxable + tax),
        )
        self.bills.append(doc)
        return doc

    def pay(self, doc: Document, day: date, rupees: float, party: Party) -> None:
        t = self.txn(day, -rupees, "expense.supplier", party)
        self.bill_payments.append(Payment(self._id(), doc.id, t.id, day, rs(rupees)))

    def loan(self, lender: Party, principal: float, disbursed: date, tenor: int = 12) -> Loan:
        loan = Loan(self._id(), lender.id, rs(principal), disbursed, tenor, 1200)
        self.loans.append(loan)
        return loan

    def instalment(
        self,
        loan: Loan,
        seq: int,
        due: date,
        principal: float,
        interest: float,
        paid: date | None = None,
        bounces: int = 0,
    ) -> Installment:
        inst = Installment(
            self._id(),
            loan.id,
            seq,
            due,
            rs(principal + interest),
            rs(principal),
            rs(interest),
            paid,
            bounces,
        )
        self.installments.append(inst)
        return inst

    def sale(self, day: date, gross: float, tax: float = 0) -> None:
        self.counter_sales.append(CounterSale(self._id(), day, rs(gross), rs(tax)))

    def data(self) -> FinancialData:
        return FinancialData(
            entity_id=uuid.UUID(int=99),
            display_name="Test Traders",
            kind=self.kind,
            segment="test",
            currency="INR",
            accounts=(Account(ACCOUNT, rs(self.opening), rs(self.overdraft)),),
            transactions=tuple(self.txns),
            counterparties=tuple(self.parties),
            invoices=tuple(self.invoices),
            invoice_payments=tuple(self.invoice_payments),
            bills=tuple(self.bills),
            bill_payments=tuple(self.bill_payments),
            loans=tuple(self.loans),
            installments=tuple(self.installments),
            counter_sales=tuple(self.counter_sales),
            data_through=self.data_through,
        )
