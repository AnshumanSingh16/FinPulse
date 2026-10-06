"""The data the analytics engine reads: a read-only snapshot of one entity.

These are plain records, independent of the database and of how the data was produced. The
repository (``persistence/repositories/financial_data.py``) builds them from PostgreSQL; tests
build them by hand. Deliberately absent: anything a lender would not have — simulation ground
truth, the simulated bureau record, and whether a lender reports to a bureau.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class Account:
    id: uuid.UUID
    opening_balance_minor: int  # balance immediately before the first transaction
    overdraft_limit_minor: int = 0


@dataclass(frozen=True, slots=True)
class Party:
    id: uuid.UUID
    name: str
    kind: str  # customer, platform, supplier, employee, lender, …


@dataclass(frozen=True, slots=True)
class Txn:
    id: uuid.UUID
    account_id: uuid.UUID
    posted_on: date
    seq: int
    amount_minor: int  # + credit, − debit
    balance_after_minor: int
    category: str | None
    counterparty_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class Document:
    """A sales invoice (party = customer) or a supplier bill (party = supplier)."""

    id: uuid.UUID
    party_id: uuid.UUID
    issued_on: date
    due_on: date
    taxable_minor: int
    tax_minor: int
    total_minor: int


@dataclass(frozen=True, slots=True)
class Payment:
    id: uuid.UUID
    document_id: uuid.UUID
    transaction_id: uuid.UUID | None
    paid_on: date
    amount_minor: int


@dataclass(frozen=True, slots=True)
class Loan:
    id: uuid.UUID
    lender_id: uuid.UUID
    principal_minor: int
    disbursed_on: date
    tenor_months: int
    annual_rate_bps: int


@dataclass(frozen=True, slots=True)
class Installment:
    id: uuid.UUID
    loan_id: uuid.UUID
    seq: int
    due_on: date
    amount_minor: int
    principal_minor: int
    interest_minor: int
    paid_on: date | None
    bounces: int = 0


@dataclass(frozen=True, slots=True)
class CounterSale:
    id: uuid.UUID
    sold_on: date
    gross_minor: int
    tax_minor: int


@dataclass(frozen=True, slots=True)
class FinancialData:
    entity_id: uuid.UUID
    display_name: str
    kind: str  # business | individual
    segment: str
    currency: str
    accounts: tuple[Account, ...]
    transactions: tuple[Txn, ...]  # ordered by seq
    counterparties: tuple[Party, ...] = ()
    invoices: tuple[Document, ...] = ()
    invoice_payments: tuple[Payment, ...] = ()
    bills: tuple[Document, ...] = ()
    bill_payments: tuple[Payment, ...] = ()
    loans: tuple[Loan, ...] = ()
    installments: tuple[Installment, ...] = ()
    counter_sales: tuple[CounterSale, ...] = ()
    # Last day the source data is complete for (e.g. a bank statement's end date). Defaults to
    # the last transaction date when unknown.
    data_through: date | None = None
