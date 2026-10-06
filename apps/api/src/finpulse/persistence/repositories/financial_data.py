"""Read an entity's financial records from PostgreSQL into the analytics engine's input.

Every query is scoped to the caller's organisation. Simulation ground truth and the simulated
bureau record are never read here: the engine only sees what a lender would see.
"""

from __future__ import annotations

import uuid
from typing import Any, Protocol, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

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
from finpulse.api.schemas.entities import EntitySummary
from finpulse.persistence import models as m
from finpulse.persistence.base import Base

T = TypeVar("T", bound=Base)


class FinancialDataSource(Protocol):
    async def list_entities(self, org_id: uuid.UUID) -> list[EntitySummary]: ...

    async def load(self, org_id: uuid.UUID, entity_id: uuid.UUID) -> FinancialData | None: ...


class PostgresFinancialDataSource:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def list_entities(self, org_id: uuid.UUID) -> list[EntitySummary]:
        async with AsyncSession(self.engine) as session:
            subjects = await session.scalars(
                select(m.Subject)
                .where(m.Subject.org_id == org_id, m.Subject.deleted_at.is_(None))
                .order_by(m.Subject.display_name)
            )
            return [
                EntitySummary(
                    id=s.id,
                    display_name=s.display_name,
                    kind=s.kind,
                    segment=s.segment,
                    data_origin=s.data_origin,
                )
                for s in subjects
            ]

    async def load(self, org_id: uuid.UUID, entity_id: uuid.UUID) -> FinancialData | None:
        async with AsyncSession(self.engine) as session:
            subject = await session.scalar(
                select(m.Subject).where(
                    m.Subject.id == entity_id,
                    m.Subject.org_id == org_id,
                    m.Subject.deleted_at.is_(None),
                )
            )
            if subject is None:
                return None
            return await _load(session, subject)


async def _load(session: AsyncSession, subject: m.Subject) -> FinancialData:
    async def rows(model: type[T], *order: Any) -> list[T]:
        subject_column = model.__table__.c.subject_id
        query = select(model).where(subject_column == subject.id).order_by(*order)
        return list((await session.scalars(query)).all())

    accounts = await rows(m.Account, m.Account.id)
    # The end date of the source statement. For synthetic subjects it is recorded with the
    # generation; only that date is read, never the ground truth.
    data_through = await session.scalar(
        select(m.SyntheticGeneration.as_of).where(m.SyntheticGeneration.subject_id == subject.id)
    )
    transactions = await rows(m.Transaction, m.Transaction.seq)
    invoices = await rows(m.Invoice, m.Invoice.issued_on, m.Invoice.number)
    invoice_payments = await rows(m.InvoicePayment, m.InvoicePayment.paid_on, m.InvoicePayment.id)
    bills = await rows(m.Bill, m.Bill.issued_on, m.Bill.number)
    bill_payments = await rows(m.BillPayment, m.BillPayment.paid_on, m.BillPayment.id)
    loans = await rows(m.Loan, m.Loan.disbursed_on, m.Loan.id)
    installments = await rows(m.LoanInstallment, m.LoanInstallment.loan_id, m.LoanInstallment.seq)
    return FinancialData(
        entity_id=subject.id,
        display_name=subject.display_name,
        kind=subject.kind,
        segment=subject.segment,
        currency=accounts[0].currency if accounts else "INR",
        accounts=tuple(
            Account(a.id, a.opening_balance_minor, a.overdraft_limit_minor) for a in accounts
        ),
        transactions=tuple(
            Txn(
                t.id,
                t.account_id,
                t.posted_on,
                t.seq,
                t.amount_minor,
                t.balance_after_minor,
                t.category,
                t.counterparty_id,
            )
            for t in transactions
        ),
        counterparties=tuple(
            Party(c.id, c.name, c.kind) for c in await rows(m.Counterparty, m.Counterparty.name)
        ),
        invoices=tuple(
            Document(
                i.id,
                i.customer_id,
                i.issued_on,
                i.due_on,
                i.taxable_minor,
                i.tax_minor,
                i.total_minor,
            )
            for i in invoices
        ),
        invoice_payments=tuple(
            Payment(p.id, p.invoice_id, p.transaction_id, p.paid_on, p.amount_minor)
            for p in invoice_payments
        ),
        bills=tuple(
            Document(
                b.id,
                b.supplier_id,
                b.issued_on,
                b.due_on,
                b.taxable_minor,
                b.tax_minor,
                b.total_minor,
            )
            for b in bills
        ),
        bill_payments=tuple(
            Payment(p.id, p.bill_id, p.transaction_id, p.paid_on, p.amount_minor)
            for p in bill_payments
        ),
        loans=tuple(
            Loan(
                x.id,
                x.lender_id,
                x.principal_minor,
                x.disbursed_on,
                x.tenor_months,
                x.annual_rate_bps,
            )
            for x in loans
        ),
        installments=tuple(
            Installment(
                i.id,
                i.loan_id,
                i.seq,
                i.due_on,
                i.amount_minor,
                i.principal_minor,
                i.interest_minor,
                i.paid_on,
                i.bounces,
            )
            for i in installments
        ),
        counter_sales=tuple(
            CounterSale(s.id, s.sold_on, s.gross_minor, s.tax_minor)
            for s in await rows(m.CounterSale, m.CounterSale.sold_on)
        ),
        data_through=data_through,
    )
