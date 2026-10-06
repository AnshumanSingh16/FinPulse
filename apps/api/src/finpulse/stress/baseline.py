"""The baseline: what a typical month looks like now, from the last complete months of data.

Every projection starts here. Averages come from the analytics ``Context`` (the same month
boundaries and category grouping as the financial metrics); debt service comes from the actual
loan schedules, not an average.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from finpulse.analytics import classify
from finpulse.analytics.context import Context, month_label
from finpulse.analytics.registry import source
from finpulse.analytics.schemas import FinancialMetricsReport, SourceRef
from finpulse.core.dates import add_months, month_end, month_start
from finpulse.core.errors import UnprocessableError

BASELINE_MONTHS = 3
# Overdraft interest is not in the data; this is the assumed annual rate (shocks may add to it).
DEFAULT_OVERDRAFT_RATE = Decimal("0.13")
OVERDRAFT_INTEREST = "bank.overdraft_interest"


@dataclass(frozen=True)
class PartyFlow:
    party_id: uuid.UUID
    name: str
    monthly_cash: int  # average monthly receipts from / payments to this party
    monthly_documents: int  # average monthly invoiced / billed value excluding GST
    share: Decimal  # of all such receipts / payments


@dataclass(frozen=True)
class LoanPosition:
    loan_id: uuid.UUID
    lender: str
    outstanding_principal: int
    annual_rate_bps: int
    remaining: list[tuple[date, int, int]]  # (due, amount, principal) still unpaid at as_of


@dataclass(frozen=True)
class Baseline:
    as_of: date
    months: list[date]  # the actual months the averages come from
    projection_months: list[date]
    opening_balance: int
    overdraft_limit: int
    overdraft_rate: Decimal
    # monthly averages (minor units)
    revenue: int
    purchases: int  # accrual, ex-GST (or supplier payments when there are no bills)
    opex: int  # non-supplier operating costs
    operating_receipts: int
    supplier_payments: int
    other_outflows: int  # drawings, GST, income tax, savings, fees (not debt, not OD interest)
    other_inflows: int  # non-operating, non-borrowing credits
    customers: list[PartyFlow]
    suppliers: list[PartyFlow]
    loans: list[LoanPosition]
    scheduled_debt: list[int]  # per projection month
    scheduled_principal: list[int]
    debt_outstanding: int
    principal_due_12m_after_horizon: int
    liquidity: dict[str, int]  # receivables, payables at as_of
    report: FinancialMetricsReport
    sources: dict[str, SourceRef] = field(default_factory=dict)

    @property
    def total_operating_outflows(self) -> int:
        return self.supplier_payments + self.opex + self.other_outflows

    @property
    def period_label(self) -> str:
        return f"{month_label(self.months[0])} to {month_label(self.months[-1])}"


def projection_months(as_of: date, horizon: int) -> list[date]:
    """Calendar months after the month containing ``as_of``."""
    first = add_months(month_start(as_of), 1)
    return [add_months(first, k) for k in range(horizon)]


def _avg(total: int, n: int) -> int:
    return round(Decimal(total) / n)


def build_baseline(ctx: Context, report: FinancialMetricsReport, horizon: int) -> Baseline:
    months = ctx.window(BASELINE_MONTHS)
    if not months:
        raise UnprocessableError(
            "A stress test needs at least one complete month of history before as_of.",
            code="insufficient_history",
        )
    n = len(months)
    start, end = months[0], month_end(months[-1])
    txns = ctx.txns_in(months)

    receipts = [t for t in txns if classify.is_operating_inflow(t.category)]
    supplier = [t for t in txns if t.category == classify.SUPPLIER_PAYMENT]
    opex = [
        t
        for t in txns
        if t.amount_minor < 0
        and t.category != classify.SUPPLIER_PAYMENT
        and classify.is_operating_expense(t.category, include_supplier_payments=False)
    ]
    counted = {t.id for t in supplier} | {t.id for t in opex}
    other_out = [
        t
        for t in txns
        if t.amount_minor < 0
        and t.id not in counted
        and t.category not in {classify.DEBT_SERVICE, OVERDRAFT_INTEREST}
    ]
    other_in = [
        t
        for t in txns
        if t.amount_minor > 0
        and not classify.is_operating_inflow(t.category)
        and t.category != classify.LOAN_DISBURSEMENT
    ]

    purchases = sum(ctx.purchases_taxable[m] for m in months)
    if not ctx.has_bills:
        purchases = sum(-t.amount_minor for t in supplier)

    # Who pays and who is paid.
    invoices = {i.id: i for i in ctx.invoices}
    by_customer_cash: dict[uuid.UUID, int] = defaultdict(int)
    for p in ctx.invoice_payments:
        if start <= p.paid_on <= end and p.document_id in invoices:
            by_customer_cash[invoices[p.document_id].party_id] += p.amount_minor
    by_customer_docs: dict[uuid.UUID, int] = defaultdict(int)
    for inv in ctx.invoices:
        if start <= inv.issued_on <= end:
            by_customer_docs[inv.party_id] += inv.taxable_minor
    by_supplier_cash: dict[uuid.UUID, int] = defaultdict(int)
    for t in supplier:
        if t.counterparty_id is not None:
            by_supplier_cash[t.counterparty_id] += -t.amount_minor
    by_supplier_docs: dict[uuid.UUID, int] = defaultdict(int)
    for b in ctx.bills:
        if start <= b.issued_on <= end:
            by_supplier_docs[b.party_id] += b.taxable_minor

    total_receipts = sum(t.amount_minor for t in receipts)
    total_supplier = sum(-t.amount_minor for t in supplier)

    def flows(
        cash: dict[uuid.UUID, int], docs: dict[uuid.UUID, int], total: int
    ) -> list[PartyFlow]:
        ids = set(cash) | set(docs)
        out = [
            PartyFlow(
                party_id=pid,
                name=ctx.parties[pid].name if pid in ctx.parties else str(pid),
                monthly_cash=_avg(cash.get(pid, 0), n),
                monthly_documents=_avg(docs.get(pid, 0), n),
                share=Decimal(cash.get(pid, 0)) / total if total else Decimal(0),
            )
            for pid in ids
        ]
        return sorted(out, key=lambda f: (-f.monthly_cash, -f.monthly_documents, str(f.party_id)))

    # Debt: actual schedules.
    p_months = projection_months(ctx.as_of, horizon)
    horizon_end = month_end(p_months[-1])
    scheduled = [0] * horizon
    scheduled_principal = [0] * horizon
    positions: list[LoanPosition] = []
    principal_due_after = 0
    debt_outstanding = 0
    for loan in ctx.loans:
        schedule = [i for i in ctx.installments if i.loan_id == loan.id]
        unpaid = sorted(
            (i for i in schedule if i.paid_on is None or i.paid_on > ctx.as_of),
            key=lambda i: i.seq,
        )
        outstanding = loan.principal_minor - sum(
            i.principal_minor for i in schedule if i.paid_on is not None and i.paid_on <= ctx.as_of
        )
        debt_outstanding += outstanding
        for inst in unpaid:
            if inst.due_on <= ctx.as_of:
                k = 0  # overdue: assumed caught up in the first projected month
            elif inst.due_on <= horizon_end:
                k = next(i for i, m in enumerate(p_months) if inst.due_on <= month_end(m))
            else:
                if inst.due_on <= horizon_end + timedelta(days=365):
                    principal_due_after += inst.principal_minor
                continue
            scheduled[k] += inst.amount_minor
            scheduled_principal[k] += inst.principal_minor
        lender = ctx.parties.get(loan.lender_id)
        positions.append(
            LoanPosition(
                loan_id=loan.id,
                lender=lender.name if lender else str(loan.lender_id),
                outstanding_principal=outstanding,
                annual_rate_bps=loan.annual_rate_bps,
                remaining=[(i.due_on, i.amount_minor, i.principal_minor) for i in unpaid],
            )
        )

    return Baseline(
        as_of=ctx.as_of,
        months=months,
        projection_months=p_months,
        opening_balance=ctx.balance_at(ctx.as_of),
        overdraft_limit=ctx.overdraft_limit,
        overdraft_rate=DEFAULT_OVERDRAFT_RATE,
        revenue=_avg(sum(ctx.revenue(m) for m in months), n),
        purchases=_avg(purchases, n),
        opex=_avg(sum(-t.amount_minor for t in opex), n),
        operating_receipts=_avg(total_receipts, n),
        supplier_payments=_avg(total_supplier, n),
        other_outflows=_avg(sum(-t.amount_minor for t in other_out), n),
        other_inflows=_avg(sum(t.amount_minor for t in other_in), n),
        customers=flows(by_customer_cash, by_customer_docs, total_receipts),
        suppliers=flows(by_supplier_cash, by_supplier_docs, total_supplier),
        loans=positions,
        scheduled_debt=scheduled,
        scheduled_principal=scheduled_principal,
        debt_outstanding=debt_outstanding,
        principal_due_12m_after_horizon=principal_due_after,
        liquidity={
            "receivables": ctx.receivables_at(ctx.as_of),
            "payables": ctx.payables_at(ctx.as_of),
        },
        report=report,
        sources={
            "receipts": source("transactions", receipts, "Operating receipts (income.*)"),
            "supplier_payments": source("transactions", supplier, "Supplier payments"),
            "opex": source("transactions", opex, "Other operating expenses"),
            "other_outflows": source("transactions", other_out, "Drawings, taxes, savings, fees"),
            "loans": source("loans", ctx.loans, "Loans outstanding at as_of"),
        },
    )
