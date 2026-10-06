"""How bank transactions are grouped for analysis, by their category.

Categories are an *input* here. Today they come from the data source (for synthetic data, the
simulation's labels); the rule-based categoriser planned for Phase 2b will assign them from the
narration. Either way the grouping below is the single definition every metric uses.
"""

from __future__ import annotations

OPERATING_INFLOW_PREFIX = "income."
SUPPLIER_PAYMENT = "expense.supplier"
DEBT_SERVICE = "debt.emi"
LOAN_DISBURSEMENT = "debt.loan_disbursement"
BOUNCE_CHARGE = "bank.bounce_charge"

# Finance costs are part of the debt picture, not of running the business.
FINANCE_COSTS = frozenset({"bank.overdraft_interest", "bank.bounce_charge", "debt.processing_fee"})
# Outflows that are not operating expenses: debt service, owner withdrawals, tax collected on
# behalf of the government (GST), income tax, and savings.
NON_OPERATING_OUTFLOWS = (
    frozenset({DEBT_SERVICE, "owner.drawings", "tax.gst", "tax.advance_tax", "personal.investment"})
    | FINANCE_COSTS
)
OPERATING_EXPENSE_PREFIXES = ("expense.", "personal.", "bank.", "cash.")


def is_operating_inflow(category: str | None) -> bool:
    """Money earned from customers: sales settlements, customer and client payments, payouts."""
    return category is not None and category.startswith(OPERATING_INFLOW_PREFIX)


def is_operating_expense(category: str | None, *, include_supplier_payments: bool) -> bool:
    """Cash spent running the business (or, for individuals, living). Uncategorised debits count
    as operating expenses — the conservative choice — and are reported in data coverage."""
    if category is None:
        return True
    if category in NON_OPERATING_OUTFLOWS:
        return False
    if category == SUPPLIER_PAYMENT:
        return include_supplier_payments
    return category.startswith(OPERATING_EXPENSE_PREFIXES)
