"""What the generator produces. Plain immutable records, independent of the database."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from finpulse.synthetic.categories import Category, Channel, CounterpartyKind

SubjectKind = Literal["business", "individual"]
InvoiceStatus = Literal["open", "partially_paid", "paid", "overdue"]
InstallmentStatus = Literal["scheduled", "paid_on_time", "paid_late", "overdue"]
BureauEventType = Literal["account_opened", "dpd_30", "dpd_60", "dpd_90", "closed"]


@dataclass(frozen=True, slots=True)
class Subject:
    id: uuid.UUID
    kind: SubjectKind
    display_name: str
    segment: str
    profile: dict[str, Any]


@dataclass(frozen=True, slots=True)
class Account:
    id: uuid.UUID
    kind: Literal["bank_current", "bank_savings"]
    institution: str
    masked_number: str
    currency: str
    opened_on: date
    opening_balance_minor: int
    overdraft_limit_minor: int


@dataclass(frozen=True, slots=True)
class Counterparty:
    id: uuid.UUID
    name: str
    kind: CounterpartyKind


@dataclass(frozen=True, slots=True)
class Transaction:
    id: uuid.UUID
    account_id: uuid.UUID
    posted_on: date
    seq: int  # global posting order; ties within a day are ordered by seq
    amount_minor: int  # signed: + credit (money in), − debit (money out)
    balance_after_minor: int
    description: str
    channel: Channel
    category: Category
    counterparty_id: uuid.UUID | None
    external_ref: str


@dataclass(frozen=True, slots=True)
class CounterSale:
    """One day's walk-in / point-of-sale takings (the shop's daily sales register)."""

    id: uuid.UUID
    sold_on: date
    gross_minor: int
    tax_minor: int
    upi_minor: int
    cash_minor: int


@dataclass(frozen=True, slots=True)
class Invoice:
    """A sales invoice raised on a customer: creates a receivable."""

    id: uuid.UUID
    number: str
    customer_id: uuid.UUID
    issued_on: date
    due_on: date
    taxable_minor: int
    tax_minor: int
    total_minor: int
    status: InvoiceStatus  # as of the dataset's as_of date


@dataclass(frozen=True, slots=True)
class Bill:
    """A purchase invoice received from a supplier: creates a payable."""

    id: uuid.UUID
    number: str
    supplier_id: uuid.UUID
    issued_on: date
    due_on: date
    taxable_minor: int
    tax_minor: int
    total_minor: int
    status: InvoiceStatus


@dataclass(frozen=True, slots=True)
class Settlement:
    """Allocation of one bank transaction to one invoice or bill."""

    id: uuid.UUID
    document_id: uuid.UUID  # invoice or bill
    # None when the payment predates the history window (an opening receivable/payable that
    # was partly paid before the statement starts).
    transaction_id: uuid.UUID | None
    paid_on: date
    amount_minor: int


@dataclass(frozen=True, slots=True)
class Loan:
    id: uuid.UUID
    lender_id: uuid.UUID
    account_id: uuid.UUID
    kind: str
    principal_minor: int
    annual_rate_bps: int
    tenor_months: int
    disbursed_on: date
    emi_minor: int
    reports_to_bureau: bool
    disbursement_transaction_id: uuid.UUID | None  # None if disbursed before the window


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
    transaction_id: uuid.UUID | None  # None if unpaid, or paid before the window
    bounces: int  # failed auto-debit attempts before payment
    status: InstallmentStatus  # as of the dataset's as_of date


@dataclass(frozen=True, slots=True)
class BureauEvent:
    """What a traditional credit bureau would have on file — evaluation data only."""

    id: uuid.UUID
    loan_id: uuid.UUID
    event_type: BureauEventType
    event_on: date  # the month-end the lender's report describes
    reported_on: date  # when the bureau receives it


@dataclass(frozen=True, slots=True)
class GroundTruth:
    archetype: str
    deteriorates: bool
    onset_date: date | None
    mechanisms: tuple[str, ...]
    narrative: str


@dataclass(frozen=True, slots=True)
class Dataset:
    scenario_code: str
    generator_version: int
    seed: int
    start_date: date
    as_of: date
    currency: str
    subject: Subject
    accounts: tuple[Account, ...]
    counterparties: tuple[Counterparty, ...]
    transactions: tuple[Transaction, ...]
    counter_sales: tuple[CounterSale, ...]
    invoices: tuple[Invoice, ...]
    invoice_payments: tuple[Settlement, ...]
    bills: tuple[Bill, ...]
    bill_payments: tuple[Settlement, ...]
    loans: tuple[Loan, ...]
    installments: tuple[Installment, ...]
    bureau_events: tuple[BureauEvent, ...]
    ground_truth: GroundTruth
    # Money that exists but is not in the bank: takings in the cash drawer and UPI collections
    # awaiting next-day settlement, at the start and end of the window. Needed to reconcile the
    # sales register to bank credits.
    opening_cash_on_hand_minor: int = 0
    opening_unsettled_upi_minor: int = 0
    cash_on_hand_minor: int = 0
    unsettled_upi_minor: int = 0
    params: dict[str, Any] = field(default_factory=dict)
