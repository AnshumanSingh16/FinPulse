"""ORM models for the tenancy root and the raw financial data of a subject.

Mirrors DATA_MODEL.md §3.1–3.3. Analysis results (metrics, passports, signals, …) arrive in later
phases. Every table below a subject cascades on delete, so removing a subject removes its data.

Money columns are ``BIGINT`` minor units; enumerations are ``TEXT`` with ``CHECK`` constraints.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from finpulse.persistence.base import Base


def _one_of(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _org() -> Mapped[uuid.UUID]:
    return mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)


def _subject() -> Mapped[uuid.UUID]:
    return mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), index=True)


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    default_currency: Mapped[str] = mapped_column(Text, server_default="INR")
    created_at: Mapped[datetime] = _created()


SUBJECT_KINDS = ("business", "individual")


class Subject(Base):
    __tablename__ = "subjects"
    __table_args__ = (
        CheckConstraint(_one_of("kind", SUBJECT_KINDS), name="kind"),
        CheckConstraint(_one_of("data_origin", ("synthetic", "imported")), name="data_origin"),
        Index(None, "org_id", "kind"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text)
    segment: Mapped[str] = mapped_column(Text)
    profile: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    data_origin: Mapped[str] = mapped_column(Text, server_default="synthetic")
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SyntheticGeneration(Base):
    """How a synthetic subject was produced, and its ground truth. Evaluation data: analytics
    engines must never read ``ground_truth``."""

    __tablename__ = "synthetic_generations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    org_id: Mapped[uuid.UUID] = _org()
    subject_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("subjects.id", ondelete="CASCADE"), unique=True
    )
    scenario_code: Mapped[str] = mapped_column(Text, index=True)
    generator_version: Mapped[int] = mapped_column(Integer)
    seed: Mapped[int] = mapped_column(BigInteger)
    start_date: Mapped[date] = mapped_column(Date)
    as_of: Mapped[date] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(Text)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB)
    ground_truth: Mapped[dict[str, Any]] = mapped_column(JSONB)
    cash_positions: Mapped[dict[str, Any]] = mapped_column(JSONB)
    dataset_fingerprint: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        CheckConstraint(_one_of("kind", ("bank_current", "bank_savings")), name="kind"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    org_id: Mapped[uuid.UUID] = _org()
    subject_id: Mapped[uuid.UUID] = _subject()
    kind: Mapped[str] = mapped_column(Text)
    institution: Mapped[str] = mapped_column(Text)
    masked_number: Mapped[str] = mapped_column(Text)
    currency: Mapped[str] = mapped_column(Text)
    opened_on: Mapped[date] = mapped_column(Date)
    opening_balance_minor: Mapped[int] = mapped_column(BigInteger)
    overdraft_limit_minor: Mapped[int] = mapped_column(BigInteger, server_default="0")
    created_at: Mapped[datetime] = _created()


COUNTERPARTY_KINDS = (
    "customer",
    "platform",
    "supplier",
    "employee",
    "landlord",
    "utility",
    "lender",
    "tax_authority",
    "bank",
    "owner",
    "merchant",
    "self",
)


class Counterparty(Base):
    __tablename__ = "counterparties"
    __table_args__ = (
        CheckConstraint(_one_of("kind", COUNTERPARTY_KINDS), name="kind"),
        UniqueConstraint("subject_id", "name", "kind"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    org_id: Mapped[uuid.UUID] = _org()
    subject_id: Mapped[uuid.UUID] = _subject()
    name: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()


CHANNELS = ("upi", "neft", "imps", "rtgs", "nach", "cash", "card", "cheque", "billpay", "internal")


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("amount_minor <> 0", name="non_zero"),
        CheckConstraint(_one_of("channel", CHANNELS), name="channel"),
        CheckConstraint(
            _one_of("category_source", ("rule", "synthetic_label", "manual")),
            name="category_source",
        ),
        UniqueConstraint("account_id", "external_ref"),
        Index(None, "subject_id", "posted_on", "seq"),
        Index(None, "subject_id", "category", "posted_on"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    org_id: Mapped[uuid.UUID] = _org()
    subject_id: Mapped[uuid.UUID] = _subject()
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    posted_on: Mapped[date] = mapped_column(Date)
    seq: Mapped[int] = mapped_column(Integer)
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(Text, server_default="INR")
    balance_after_minor: Mapped[int] = mapped_column(BigInteger)
    description: Mapped[str] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(Text)
    category_source: Mapped[str] = mapped_column(Text, server_default="synthetic_label")
    counterparty_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("counterparties.id", ondelete="SET NULL"), index=True
    )
    external_ref: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()


class CounterSale(Base):
    """Daily walk-in sales register (point-of-sale takings)."""

    __tablename__ = "counter_sales"
    __table_args__ = (
        CheckConstraint("upi_minor + cash_minor = gross_minor", name="split"),
        UniqueConstraint("subject_id", "sold_on"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    org_id: Mapped[uuid.UUID] = _org()
    subject_id: Mapped[uuid.UUID] = _subject()
    sold_on: Mapped[date] = mapped_column(Date)
    gross_minor: Mapped[int] = mapped_column(BigInteger)
    tax_minor: Mapped[int] = mapped_column(BigInteger)
    upi_minor: Mapped[int] = mapped_column(BigInteger)
    cash_minor: Mapped[int] = mapped_column(BigInteger)


DOCUMENT_STATUSES = ("open", "partially_paid", "paid", "overdue")


class Invoice(Base):
    """Sales invoice → receivable."""

    __tablename__ = "invoices"
    __table_args__ = (
        CheckConstraint("taxable_minor + tax_minor = total_minor", name="total"),
        CheckConstraint(_one_of("status", DOCUMENT_STATUSES), name="status"),
        UniqueConstraint("subject_id", "number"),
        Index(None, "subject_id", "issued_on"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    org_id: Mapped[uuid.UUID] = _org()
    subject_id: Mapped[uuid.UUID] = _subject()
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("counterparties.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[str] = mapped_column(Text)
    issued_on: Mapped[date] = mapped_column(Date)
    due_on: Mapped[date] = mapped_column(Date)
    taxable_minor: Mapped[int] = mapped_column(BigInteger)
    tax_minor: Mapped[int] = mapped_column(BigInteger)
    total_minor: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(Text)  # as of the dataset's as_of date


class InvoicePayment(Base):
    __tablename__ = "invoice_payments"
    __table_args__ = (CheckConstraint("amount_minor > 0", name="positive"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    org_id: Mapped[uuid.UUID] = _org()
    subject_id: Mapped[uuid.UUID] = _subject()
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), index=True
    )
    # NULL when the payment predates the bank history (opening receivable partly paid earlier).
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"), index=True
    )
    paid_on: Mapped[date] = mapped_column(Date)
    amount_minor: Mapped[int] = mapped_column(BigInteger)


class Bill(Base):
    """Purchase invoice from a supplier → payable."""

    __tablename__ = "bills"
    __table_args__ = (
        CheckConstraint("taxable_minor + tax_minor = total_minor", name="total"),
        CheckConstraint(_one_of("status", DOCUMENT_STATUSES), name="status"),
        UniqueConstraint("subject_id", "supplier_id", "number"),
        Index(None, "subject_id", "issued_on"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    org_id: Mapped[uuid.UUID] = _org()
    subject_id: Mapped[uuid.UUID] = _subject()
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("counterparties.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[str] = mapped_column(Text)
    issued_on: Mapped[date] = mapped_column(Date)
    due_on: Mapped[date] = mapped_column(Date)
    taxable_minor: Mapped[int] = mapped_column(BigInteger)
    tax_minor: Mapped[int] = mapped_column(BigInteger)
    total_minor: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(Text)


class BillPayment(Base):
    __tablename__ = "bill_payments"
    __table_args__ = (CheckConstraint("amount_minor > 0", name="positive"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    org_id: Mapped[uuid.UUID] = _org()
    subject_id: Mapped[uuid.UUID] = _subject()
    bill_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bills.id", ondelete="CASCADE"), index=True
    )
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"), index=True
    )
    paid_on: Mapped[date] = mapped_column(Date)
    amount_minor: Mapped[int] = mapped_column(BigInteger)


class Loan(Base):
    __tablename__ = "loans"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    org_id: Mapped[uuid.UUID] = _org()
    subject_id: Mapped[uuid.UUID] = _subject()
    lender_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("counterparties.id", ondelete="CASCADE")
    )
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(Text)
    principal_minor: Mapped[int] = mapped_column(BigInteger)
    annual_rate_bps: Mapped[int] = mapped_column(Integer)
    tenor_months: Mapped[int] = mapped_column(SmallInteger)
    disbursed_on: Mapped[date] = mapped_column(Date)
    emi_minor: Mapped[int] = mapped_column(BigInteger)
    reports_to_bureau: Mapped[bool] = mapped_column(Boolean)
    # NULL when the loan was taken before the bank history starts.
    disbursement_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE")
    )


INSTALLMENT_STATUSES = ("scheduled", "paid_on_time", "paid_late", "overdue")


class LoanInstallment(Base):
    __tablename__ = "loan_installments"
    __table_args__ = (
        CheckConstraint("principal_minor + interest_minor = amount_minor", name="amount"),
        CheckConstraint(_one_of("status", INSTALLMENT_STATUSES), name="status"),
        UniqueConstraint("loan_id", "seq"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    org_id: Mapped[uuid.UUID] = _org()
    subject_id: Mapped[uuid.UUID] = _subject()
    loan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("loans.id", ondelete="CASCADE"))
    seq: Mapped[int] = mapped_column(SmallInteger)
    due_on: Mapped[date] = mapped_column(Date)
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    principal_minor: Mapped[int] = mapped_column(BigInteger)
    interest_minor: Mapped[int] = mapped_column(BigInteger)
    paid_on: Mapped[date | None] = mapped_column(Date)
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE")
    )
    bounces: Mapped[int] = mapped_column(SmallInteger, server_default="0")
    status: Mapped[str] = mapped_column(Text)


BUREAU_EVENT_TYPES = ("account_opened", "dpd_30", "dpd_60", "dpd_90", "closed")


class SimulatedBureauEvent(Base):
    """What a traditional bureau would hold. Evaluation only — never an analytics input."""

    __tablename__ = "simulated_bureau_events"
    __table_args__ = (
        CheckConstraint(_one_of("event_type", BUREAU_EVENT_TYPES), name="event_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    org_id: Mapped[uuid.UUID] = _org()
    subject_id: Mapped[uuid.UUID] = _subject()
    loan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("loans.id", ondelete="CASCADE"))
    event_type: Mapped[str] = mapped_column(Text)
    event_on: Mapped[date] = mapped_column(Date)
    reported_on: Mapped[date] = mapped_column(Date)
