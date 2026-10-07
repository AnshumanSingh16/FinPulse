"""Integrity checks on an entity's financial data before any engine reads it.

Financial records can be wrong, tampered with, or crafted to mislead (an "income" of ₹10¹⁵, a
bank balance that does not follow from its transactions, a payment larger than its invoice).
Every engine — analytics, passport, early warning, stress, and the evidence the AI agents read —
starts from data that has passed these checks; data that fails is refused with
``422 data_integrity_failed`` rather than scored.

The checks are structural and cheap (one pass over the records). They catch impossible or
inconsistent data; they cannot catch plausible-looking fabrication, which is why FinPulse reads
bank-verified records and states what it cannot see (docs/SECURITY.md).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from finpulse.analytics.inputs import FinancialData
from finpulse.core.errors import UnprocessableError

MAX_ABS_MINOR = 10**13  # ₹100 billion in paise: far beyond any MSME or individual
MAX_RECORDS = 500_000  # per table, per entity
MAX_TEXT = 200  # characters in a name or label
EARLIEST = date(1990, 1, 1)
LATEST = date(2100, 1, 1)
MAX_REPORTED_ISSUES = 20


def integrity_issues(data: FinancialData) -> list[str]:
    """Every problem found, most fundamental first (empty when the data is consistent)."""
    issues: list[str] = []

    def bad(message: str) -> None:
        issues.append(message)

    tables = {
        "transactions": data.transactions,
        "invoices": data.invoices,
        "bills": data.bills,
        "invoice_payments": data.invoice_payments,
        "bill_payments": data.bill_payments,
        "installments": data.installments,
        "counter_sales": data.counter_sales,
    }
    for name, rows in tables.items():
        if len(rows) > MAX_RECORDS:
            bad(f"{name}: {len(rows)} records exceeds the limit of {MAX_RECORDS}.")
    if issues:
        return issues  # too large to check further

    for label, text in [("display_name", data.display_name), ("segment", data.segment)] + [
        (f"counterparty {p.id}", p.name) for p in data.counterparties
    ]:
        if len(text) > MAX_TEXT:
            bad(f"{label}: longer than {MAX_TEXT} characters.")

    def amount(where: str, value: int) -> None:
        if abs(value) > MAX_ABS_MINOR:
            bad(f"{where}: amount {value} is outside the plausible range.")

    def when(where: str, value: date | None) -> None:
        if value is not None and not EARLIEST <= value < LATEST:
            bad(f"{where}: date {value} is outside the plausible range.")

    # The ledger: every balance must follow from the previous one and the amount.
    accounts = {a.id: a for a in data.accounts}
    balance = {a.id: a.opening_balance_minor for a in data.accounts}
    for a in data.accounts:
        amount(f"account {a.id} opening balance", a.opening_balance_minor)
        amount(f"account {a.id} overdraft limit", a.overdraft_limit_minor)
        if a.overdraft_limit_minor < 0:
            bad(f"account {a.id}: negative overdraft limit.")
    parties = {p.id for p in data.counterparties}
    for t in data.transactions:
        where = f"transaction {t.id}"
        amount(where, t.amount_minor)
        when(where, t.posted_on)
        if t.account_id not in accounts:
            bad(f"{where}: unknown account.")
            continue
        if t.counterparty_id is not None and t.counterparty_id not in parties:
            bad(f"{where}: unknown counterparty.")
        expected = balance[t.account_id] + t.amount_minor
        if t.balance_after_minor != expected:
            bad(
                f"{where}: balance {t.balance_after_minor} does not follow from the ledger "
                f"({expected})."
            )
        balance[t.account_id] = t.balance_after_minor
        if len(issues) >= MAX_REPORTED_ISSUES:
            return issues

    # Documents and their payments: totals add up, payments never exceed what was billed.
    for kind, docs, payments in [
        ("invoice", data.invoices, data.invoice_payments),
        ("bill", data.bills, data.bill_payments),
    ]:
        by_id = {d.id: d for d in docs}
        for d in docs:
            where = f"{kind} {d.id}"
            amount(where, d.total_minor)
            when(where, d.issued_on)
            when(where, d.due_on)
            if min(d.taxable_minor, d.tax_minor, d.total_minor) < 0:
                bad(f"{where}: negative amount.")
            if d.taxable_minor + d.tax_minor != d.total_minor:
                bad(f"{where}: total does not equal taxable value plus tax.")
            if d.due_on < d.issued_on:
                bad(f"{where}: due before it was issued.")
            if d.party_id not in parties:
                bad(f"{where}: unknown counterparty.")
        paid: dict[object, int] = defaultdict(int)
        for pay in payments:
            where = f"{kind} payment {pay.id}"
            amount(where, pay.amount_minor)
            when(where, pay.paid_on)
            if pay.amount_minor <= 0:
                bad(f"{where}: non-positive amount.")
            if pay.document_id not in by_id:
                bad(f"{where}: unknown {kind}.")
                continue
            paid[pay.document_id] += pay.amount_minor
        for doc_id, total in paid.items():
            if total > by_id[doc_id].total_minor:  # type: ignore[index]
                bad(f"{kind} {doc_id}: payments exceed the amount billed.")

    loans = {loan.id: loan for loan in data.loans}
    for loan in data.loans:
        where = f"loan {loan.id}"
        amount(where, loan.principal_minor)
        when(where, loan.disbursed_on)
        if loan.principal_minor <= 0 or not 1 <= loan.tenor_months <= 600:
            bad(f"{where}: implausible principal or tenor.")
        if not 0 <= loan.annual_rate_bps <= 10_000:
            bad(f"{where}: interest rate outside 0–100%.")
    for i in data.installments:
        where = f"instalment {i.id}"
        amount(where, i.amount_minor)
        when(where, i.due_on)
        when(where, i.paid_on)
        if i.loan_id not in loans:
            bad(f"{where}: unknown loan.")
        if i.principal_minor + i.interest_minor != i.amount_minor or i.amount_minor < 0:
            bad(f"{where}: principal plus interest does not equal the instalment.")
    for s in data.counter_sales:
        amount(f"counter sale {s.id}", s.gross_minor)
        when(f"counter sale {s.id}", s.sold_on)
        if s.gross_minor < 0 or s.tax_minor < 0 or s.tax_minor > s.gross_minor:
            bad(f"counter sale {s.id}: implausible amounts.")
    return issues[:MAX_REPORTED_ISSUES]


def check_integrity(data: FinancialData) -> None:
    """Refuse data that is impossible or internally inconsistent."""
    issues = integrity_issues(data)
    if issues:
        raise UnprocessableError(
            f"The financial data for this entity failed {len(issues)} integrity check(s) and "
            "cannot be analysed.",
            code="data_integrity_failed",
            extra={"issues": issues},
        )
