"""
Canonical data model.

FinPilot works on three tables, kept separate on purpose because they answer different questions:

* ``ledger``      money that actually moved (bank / cash book). Drives revenue, expenses and cash.
* ``obligations`` invoices and bills: receivables and payables with due dates and a status.
                  Drives "what is owed", overdue amounts and the cash forecast.
* ``balances``    dated account balances (e.g. from a bank statement). The ONLY source of an actual
                  cash position — FinPilot never infers cash from revenue minus expenses.
"""

from __future__ import annotations

from dataclasses import dataclass

LEDGER_COLUMNS = [
    "txn_id",
    "date",
    "description",
    "counterparty",
    "category",
    "direction",  # "in" | "out"
    "amount",  # always positive, in rupees
    "payment_mode",
    "reference",
]
LEDGER_REQUIRED = ["date", "description", "category", "amount"]

OBLIGATION_COLUMNS = [
    "item_id",
    "kind",  # "receivable" | "payable"
    "counterparty",
    "description",
    "category",
    "amount",
    "issue_date",
    "due_date",
    "status",  # "paid" | "pending"
    "paid_date",
]
OBLIGATION_REQUIRED = ["kind", "counterparty", "amount", "due_date", "status"]

BALANCE_COLUMNS = ["as_of", "account", "balance"]
BALANCE_REQUIRED = ["as_of", "balance"]

# How each category is treated. Anything not listed is classified by direction and flagged.
#   revenue            counts as revenue
#   operating          an operating expense (counts towards estimated operating profit)
#   capex              an asset purchase: a cash outflow, not an operating expense
#   financing_in       loans received, owner capital: cash in, not revenue
#   financing_out      loan repayments: cash out, not an operating expense (interest not split out)
#   drawings           owner withdrawals: cash out, not an expense of the business
#   tax_remittance     GST / TDS paid to government: cash out; excluded from operating expenses
#   transfer           movement between own accounts: excluded from everything except cash
#   other_in           other inflows (refunds, interest): cash in, not revenue
CATEGORY_CLASS: dict[str, str] = {
    "sales": "revenue",
    "sales - b2b": "revenue",
    "sales - retail": "revenue",
    "service income": "revenue",
    "raw materials": "operating",
    "packaging": "operating",
    "salaries": "operating",
    "rent": "operating",
    "electricity": "operating",
    "utilities": "operating",
    "logistics": "operating",
    "marketing": "operating",
    "software": "operating",
    "repairs & maintenance": "operating",
    "professional fees": "operating",
    "bank charges": "operating",
    "office supplies": "operating",
    "travel": "operating",
    "insurance": "operating",
    "staff welfare": "operating",
    "purchases": "operating",
    "fuel": "operating",
    "cash withdrawal": "transfer",
    "equipment": "capex",
    "machinery": "capex",
    "loan received": "financing_in",
    "owner capital": "financing_in",
    "loan emi": "financing_out",
    "loan repayment": "financing_out",
    "owner drawings": "drawings",
    "gst payment": "tax_remittance",
    "tds payment": "tax_remittance",
    "income tax": "tax_remittance",
    "transfer": "transfer",
    "refund received": "other_in",
    "interest received": "other_in",
}

CLASS_LABEL = {
    "revenue": "Revenue",
    "operating": "Operating expense",
    "capex": "Asset purchase (capex)",
    "financing_in": "Financing inflow",
    "financing_out": "Loan repayment",
    "drawings": "Owner drawings",
    "tax_remittance": "Tax paid to government",
    "transfer": "Transfer between own accounts",
    "other_in": "Other inflow",
    "unclassified_out": "Unclassified outflow (treated as operating)",
    "unclassified_in": "Unclassified inflow (not counted as revenue)",
}


def classify(category: str, direction: str) -> str:
    """Accounting class for a ledger row. Unknown categories are classified conservatively."""
    cls = CATEGORY_CLASS.get(str(category).strip().lower())
    if cls is None:
        return "unclassified_out" if direction == "out" else "unclassified_in"
    # A category on the "wrong" side (e.g. a refund booked under Raw materials) stays in its class;
    # the sign is handled by direction.
    return cls


@dataclass(frozen=True)
class Evidence:
    """What every result carries: how it was computed, on what, and what it can't tell you."""

    method: str
    assumptions: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    record_ids: tuple[str, ...] = ()
    period: tuple[str, str] | None = None
    unverified: tuple[str, ...] = ()  # what the records can't confirm (shown as "What I couldn't verify")

    def to_dict(self) -> dict:
        return {
            "method": self.method,
            "assumptions": list(self.assumptions),
            "limitations": list(self.limitations),
            "record_ids": list(self.record_ids),
            "period": list(self.period) if self.period else None,
            "unverified": list(self.unverified),
        }
