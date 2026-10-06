"""Turn a generated synthetic dataset into the analytics engine's input — the same shape the
database repository produces, minus anything a lender would not see (ground truth, bureau)."""

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
from finpulse.synthetic import Dataset


def to_financial_data(ds: Dataset) -> FinancialData:
    return FinancialData(
        entity_id=ds.subject.id,
        display_name=ds.subject.display_name,
        kind=ds.subject.kind,
        segment=ds.subject.segment,
        currency=ds.currency,
        accounts=tuple(
            Account(a.id, a.opening_balance_minor, a.overdraft_limit_minor) for a in ds.accounts
        ),
        transactions=tuple(
            Txn(
                t.id,
                t.account_id,
                t.posted_on,
                t.seq,
                t.amount_minor,
                t.balance_after_minor,
                str(t.category),
                t.counterparty_id,
            )
            for t in ds.transactions
        ),
        counterparties=tuple(Party(c.id, c.name, str(c.kind)) for c in ds.counterparties),
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
            for i in ds.invoices
        ),
        invoice_payments=tuple(
            Payment(p.id, p.document_id, p.transaction_id, p.paid_on, p.amount_minor)
            for p in ds.invoice_payments
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
            for b in ds.bills
        ),
        bill_payments=tuple(
            Payment(p.id, p.document_id, p.transaction_id, p.paid_on, p.amount_minor)
            for p in ds.bill_payments
        ),
        loans=tuple(
            Loan(
                loan.id,
                loan.lender_id,
                loan.principal_minor,
                loan.disbursed_on,
                loan.tenor_months,
                loan.annual_rate_bps,
            )
            for loan in ds.loans
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
            for i in ds.installments
        ),
        counter_sales=tuple(
            CounterSale(s.id, s.sold_on, s.gross_minor, s.tax_minor) for s in ds.counter_sales
        ),
        data_through=ds.as_of,
    )
