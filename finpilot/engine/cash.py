"""
Cash position and obligations.

Cash comes only from a dated balance (e.g. a bank statement) rolled forward with the ledger rows
dated after it. With no dated balance, the cash position is unknown — FinPilot says so instead of
using revenue minus expenses.
"""

from __future__ import annotations

import pandas as pd

from finpilot.data.schema import Evidence
from finpilot.engine.common import money, prepare_ledger, ts


def cash_position(ledger: pd.DataFrame, balances: pd.DataFrame | None, as_of, account: str | None = None) -> dict:
    target = ts(as_of)
    if balances is None or balances.empty:
        return {
            "status": "unknown",
            "message": (
                "No dated opening balance was provided, so the actual cash position can't be known. "
                "Add a bank balance with its date (e.g. from a bank statement)."
            ),
            "missing": ["dated opening balance"],
            "evidence": Evidence(method="Cash needs a dated balance; none supplied.").to_dict(),
        }
    bal = balances.copy()
    bal["as_of"] = pd.to_datetime(bal["as_of"]).dt.normalize()
    if account is not None and "account" in bal:
        bal = bal[bal["account"] == account]
    usable = bal[bal["as_of"] <= target].sort_values("as_of")
    if usable.empty:
        return {
            "status": "unknown",
            "message": f"The earliest balance is dated after {target.date()}; cash on that date can't be derived.",
            "missing": [f"a balance dated on or before {target.date()}"],
            "evidence": Evidence(method="No balance on or before the requested date.").to_dict(),
        }
    df = prepare_ledger(ledger)
    if account is not None and "account" in df:
        df = df[df["account"] == account]

    # Reconcile every later statement balance against the ledger, starting from the earliest.
    first = usable.iloc[0]
    checks = []
    for row in bal.sort_values("as_of").iloc[1:].itertuples():
        moved = df[(df["date"] > first["as_of"]) & (df["date"] <= row.as_of)]["signed"].sum()
        computed = float(first["balance"]) + float(moved)
        checks.append(
            {
                "as_of": str(row.as_of.date()),
                "stated_balance": money(row.balance),
                "computed_from_ledger": money(computed),
                "difference": money(row.balance - computed),
                "reconciled": abs(row.balance - computed) < 1.0,
            }
        )

    anchor = usable.iloc[-1]  # the latest balance on or before the date
    rows = df[(df["date"] > anchor["as_of"]) & (df["date"] <= target)]
    cash = float(anchor["balance"]) + float(rows["signed"].sum())
    limitations = ["Assumes the ledger records every bank movement after the balance date."]
    unreconciled = [c for c in checks if not c["reconciled"]]
    if unreconciled:
        limitations.append(
            "The ledger does not reconcile with a later statement balance: "
            + "; ".join(f"{c['as_of']} differs by {c['difference']:,.0f}" for c in unreconciled)
        )
    if df["date"].max() < target:
        limitations.append(f"The ledger ends on {df['date'].max().date()}; later movements are unknown.")
    return {
        "status": "ok",
        "as_of": str(target.date()),
        "cash_balance": money(cash),
        "anchor_balance": {"as_of": str(anchor["as_of"].date()), "balance": money(anchor["balance"])},
        "net_movement_since_anchor": money(rows["signed"].sum()),
        "transactions_since_anchor": int(len(rows)),
        "reconciliation": checks,
        "evidence": Evidence(
            method="Cash = latest dated balance on or before the date + inflows − outflows recorded after it.",
            limitations=tuple(limitations),
            record_ids=tuple(rows["txn_id"]),
            period=(str(anchor["as_of"].date()), str(target.date())),
        ).to_dict(),
    }


def _obl(obligations: pd.DataFrame) -> pd.DataFrame:
    o = obligations.copy()
    for c in ("issue_date", "due_date", "paid_date"):
        if c in o:
            o[c] = pd.to_datetime(o[c]).dt.normalize()
    return o


def obligations_status(obligations: pd.DataFrame | None, as_of) -> dict:
    """Paid, pending (not yet due) and overdue amounts for receivables and payables."""
    target = ts(as_of)
    if obligations is None or obligations.empty:
        return {
            "status": "insufficient_data",
            "message": "No invoices or bills were provided, so amounts owed are unknown.",
            "missing": ["receivables/payables with due dates"],
            "evidence": Evidence(method="No obligations data.").to_dict(),
        }
    o = _obl(obligations)
    out = {"status": "ok", "as_of": str(target.date())}
    for kind in ("receivable", "payable"):
        k = o[o["kind"] == kind]
        pend = k[k["status"] == "pending"]
        overdue = pend[pend["due_date"] < target]
        not_due = pend[pend["due_date"] >= target]
        ages = (target - overdue["due_date"]).dt.days
        buckets = {
            "1-30 days": money(overdue.loc[ages.between(1, 30), "amount"].sum()),
            "31-60 days": money(overdue.loc[ages.between(31, 60), "amount"].sum()),
            "61-90 days": money(overdue.loc[ages.between(61, 90), "amount"].sum()),
            "90+ days": money(overdue.loc[ages > 90, "amount"].sum()),
        }
        out[kind + "s"] = {
            "paid": money(k.loc[k["status"] == "paid", "amount"].sum()),
            "pending_not_due": money(not_due["amount"].sum()),
            "overdue": money(overdue["amount"].sum()),
            "overdue_count": int(len(overdue)),
            "overdue_by_age": buckets,
            "overdue_items": [
                {
                    "item_id": r.item_id,
                    "counterparty": r.counterparty,
                    "amount": money(r.amount),
                    "due_date": str(r.due_date.date()),
                    "days_overdue": int((target - r.due_date).days),
                }
                for r in overdue.sort_values("due_date").itertuples()
            ],
        }
    out["evidence"] = Evidence(
        method="Overdue = status pending and due date before the as-of date. Paid = status paid.",
        assumptions=("Statuses are as recorded in the uploaded invoices and bills.",),
        record_ids=tuple(o.loc[o["status"] == "pending", "item_id"]),
    ).to_dict()
    return out


def upcoming_payments(obligations: pd.DataFrame | None, as_of, days: int = 30) -> dict:
    target = ts(as_of)
    if obligations is None or obligations.empty:
        return {
            "status": "insufficient_data",
            "message": "No bills were provided, so upcoming payments are unknown.",
            "missing": ["payables with due dates"],
            "evidence": Evidence(method="No obligations data.").to_dict(),
        }
    o = _obl(obligations)
    pend = o[(o["kind"] == "payable") & (o["status"] == "pending")]
    end = target + pd.Timedelta(days=days)
    overdue = pend[pend["due_date"] < target]
    upcoming = pend[(pend["due_date"] >= target) & (pend["due_date"] <= end)].sort_values("due_date")

    def items(df):
        return [
            {
                "item_id": r.item_id,
                "counterparty": r.counterparty,
                "description": r.description,
                "category": r.category,
                "amount": money(r.amount),
                "due_date": str(r.due_date.date()),
            }
            for r in df.itertuples()
        ]

    return {
        "status": "ok",
        "window": {"start": str(target.date()), "end": str(end.date())},
        "overdue_total": money(overdue["amount"].sum()),
        "overdue": items(overdue.sort_values("due_date")),
        "upcoming_total": money(upcoming["amount"].sum()),
        "upcoming": items(upcoming),
        "evidence": Evidence(
            method="Pending payables due within the window, plus any already overdue.",
            limitations=(
                "Only bills that were uploaded are included; regular costs without a bill (e.g. "
                "raw-material purchases not yet invoiced) are not.",
            ),
            record_ids=tuple(overdue["item_id"]) + tuple(upcoming["item_id"]),
            period=(str(target.date()), str(end.date())),
        ).to_dict(),
    }
