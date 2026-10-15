"""Small hand-built datasets whose every figure can be checked by hand, plus the fixed demo data."""

import pandas as pd
import pytest

from finpilot.data.demo import load_demo


def ledger_frame(rows):
    df = pd.DataFrame(
        rows,
        columns=["txn_id", "date", "description", "counterparty", "category", "direction", "amount"],
    )
    df["date"] = pd.to_datetime(df["date"])
    df["payment_mode"] = "NEFT"
    df["reference"] = ""
    return df


@pytest.fixture
def tiny():
    """March and April 2026 for a fictional shop. Hand-checkable."""
    ledger = ledger_frame(
        [
            ("T1", "2026-03-02", "Sale", "A", "Sales", "in", 100_000),
            ("T2", "2026-03-05", "Rent", "Landlord", "Rent", "out", 20_000),
            ("T3", "2026-03-10", "Stock", "Supplier", "Raw materials", "out", 30_000),
            ("T4", "2026-03-15", "Loan", "Bank", "Loan Received", "in", 50_000),
            ("T5", "2026-03-20", "Laptop", "Shop", "Equipment", "out", 40_000),
            ("T6", "2026-03-25", "Owner", "Owner", "Owner Drawings", "out", 10_000),
            ("T7", "2026-04-02", "Sale", "B", "Sales", "in", 120_000),
            ("T8", "2026-04-05", "Rent", "Landlord", "Rent", "out", 20_000),
            ("T9", "2026-04-10", "Stock", "Supplier", "Raw materials", "out", 45_000),
            ("T10", "2026-04-12", "Mystery", "Unknown", "Misc stuff", "out", 5_000),
            ("T11", "2026-04-20", "GST", "GSTN", "GST Payment", "out", 8_000),
        ]
    )
    balances = pd.DataFrame(
        {"as_of": pd.to_datetime(["2026-02-28"]), "account": ["Bank"], "balance": [60_000.0]}
    )
    obligations = pd.DataFrame(
        [
            ("INV-1", "receivable", "C", "Invoice", "Sales", 40_000, "2026-04-01", "2026-04-20", "pending", None),
            ("INV-2", "receivable", "D", "Invoice", "Sales", 25_000, "2026-04-15", "2026-05-15", "pending", None),
            ("BILL-1", "payable", "Landlord", "Rent May", "Rent", 20_000, None, "2026-05-05", "pending", None),
            ("BILL-2", "payable", "Supplier", "Stock", "Raw materials", 15_000, "2026-04-01", "2026-04-25", "pending", None),
            ("INV-0", "receivable", "A", "Invoice", "Sales", 100_000, "2026-02-01", "2026-03-02", "paid", "2026-03-02"),
        ],
        columns=["item_id", "kind", "counterparty", "description", "category", "amount", "issue_date", "due_date", "status", "paid_date"],
    )
    for c in ("issue_date", "due_date", "paid_date"):
        obligations[c] = pd.to_datetime(obligations[c])
    return {"ledger": ledger, "balances": balances, "obligations": obligations, "as_of": "2026-04-30"}


@pytest.fixture(scope="session")
def demo():
    return load_demo()
