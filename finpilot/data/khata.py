"""
Quick entries (the khata): sales, expenses, udhaar given, payments received, supplier bills and bill
payments. Each function takes the book's tables and returns new tables plus an undo record, so an
entry can be reversed exactly. They follow the engine's accounting rules:

* a sale or payment received is a ledger inflow (revenue on receipt — cash basis);
* udhaar given / a supplier bill is an obligation (receivable / payable), NOT a ledger row, so it
  is never counted as revenue or expense until money actually moves;
* a payment against udhaar settles the oldest pending items first; a part-payment splits the item
  into a paid part and a still-pending remainder, so nothing is double-counted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd

from finpilot.data.schema import BALANCE_COLUMNS, LEDGER_COLUMNS, OBLIGATION_COLUMNS
from finpilot.engine.common import fmt_inr, money

KINDS = ("sale", "expense", "credit_sale", "payment_in", "bill", "payment_out")
MODES = ("cash", "upi", "bank", "card", "cheque")


class EntryError(ValueError):
    """The entry can't be recorded as given (message is shown to the owner)."""


@dataclass
class Tables:
    ledger: pd.DataFrame
    obligations: pd.DataFrame | None
    balances: pd.DataFrame | None = None

    def copy(self) -> "Tables":
        return Tables(self.ledger.copy(), None if self.obligations is None else self.obligations.copy(), None if self.balances is None else self.balances.copy())


@dataclass
class Result:
    tables: Tables
    entry_id: str
    summary: str
    undo: dict = field(default_factory=dict)
    settled: list[dict] = field(default_factory=list)
    unapplied: float = 0.0


def _next_id(existing, prefix: str, width: int) -> str:
    n = 0
    pat = re.compile(rf"^{re.escape(prefix)}(\d+)")
    for v in existing:
        m = pat.match(str(v))
        if m:
            n = max(n, int(m.group(1)))
    return f"{prefix}{n + 1:0{width}d}"


def _empty_obligations() -> pd.DataFrame:
    df = pd.DataFrame(columns=OBLIGATION_COLUMNS)
    for c in ("issue_date", "due_date", "paid_date"):
        df[c] = pd.to_datetime(df[c])
    df["amount"] = df["amount"].astype(float)
    return df


def empty_ledger() -> pd.DataFrame:
    df = pd.DataFrame(columns=LEDGER_COLUMNS)
    df["date"] = pd.to_datetime(df["date"])
    df["amount"] = df["amount"].astype(float)
    return df


def empty_balances() -> pd.DataFrame:
    df = pd.DataFrame(columns=BALANCE_COLUMNS)
    df["as_of"] = pd.to_datetime(df["as_of"])
    return df


def _add_ledger(t: Tables, date, amount, direction, category, party, description, mode) -> str:
    tid = _next_id(t.ledger["txn_id"], "E", 5)
    row = {"txn_id": tid, "date": pd.Timestamp(date).normalize(), "description": description, "counterparty": party, "category": category,
           "direction": direction, "amount": money(amount), "payment_mode": mode.upper() if mode else "", "reference": "Quick entry"}
    t.ledger = pd.concat([t.ledger, pd.DataFrame([row])], ignore_index=True) if len(t.ledger) else pd.DataFrame([row], columns=LEDGER_COLUMNS)
    t.ledger["date"] = pd.to_datetime(t.ledger["date"])
    return tid


def _add_obligation(t: Tables, kind, party, amount, issue, due, description, category) -> str:
    o = t.obligations if t.obligations is not None else _empty_obligations()
    iid = _next_id(o["item_id"], "K-", 4)
    row = {"item_id": iid, "kind": kind, "counterparty": party, "description": description, "category": category, "amount": money(amount),
           "issue_date": pd.Timestamp(issue).normalize(), "due_date": pd.Timestamp(due).normalize(), "status": "pending", "paid_date": pd.NaT}
    o = pd.concat([o, pd.DataFrame([row])], ignore_index=True) if len(o) else pd.DataFrame([row], columns=OBLIGATION_COLUMNS)
    for c in ("issue_date", "due_date", "paid_date"):
        o[c] = pd.to_datetime(o[c])
    t.obligations = o
    return iid


def _settle(t: Tables, kind: str, party: str, amount: float, date) -> tuple[list[dict], float, list[dict], list[str]]:
    """Settle the oldest pending items for this party. Returns (settled, leftover, rows_before, new_ids)."""
    o = t.obligations
    if o is None or not len(o):
        return [], amount, [], []
    pend = o[(o["kind"] == kind) & (o["status"] == "pending") & (o["counterparty"].str.lower() == party.lower())].sort_values(["due_date", "item_id"])
    left = round(amount, 2)
    settled, before, new_ids = [], [], []
    for idx, r in pend.iterrows():
        if left <= 0.004:
            break
        before.append({k: (None if pd.isna(v) else (str(v.date()) if isinstance(v, pd.Timestamp) else v)) for k, v in r.items()})
        if left + 0.004 >= r["amount"]:
            o.loc[idx, ["status", "paid_date"]] = ["paid", pd.Timestamp(date).normalize()]
            settled.append({"item_id": r["item_id"], "amount": float(r["amount"]), "full": True})
            left = round(left - float(r["amount"]), 2)
        else:  # part-payment: split into a paid part and the pending remainder
            n = 1
            while f"{r['item_id']}-P{n}" in set(o["item_id"]):
                n += 1
            pid = f"{r['item_id']}-P{n}"
            paid = r.to_dict() | {"item_id": pid, "amount": money(left), "status": "paid", "paid_date": pd.Timestamp(date).normalize(),
                                  "description": f"{r['description']} (part payment)".strip()}
            o.loc[idx, "amount"] = money(float(r["amount"]) - left)
            o = pd.concat([o, pd.DataFrame([paid])], ignore_index=True)
            new_ids.append(pid)
            settled.append({"item_id": r["item_id"], "amount": money(left), "full": False})
            left = 0.0
    for c in ("issue_date", "due_date", "paid_date"):
        o[c] = pd.to_datetime(o[c])
    t.obligations = o
    return settled, max(left, 0.0), before, new_ids


def record(tables: Tables, kind: str, amount: float, date, party: str = "", category: str = "", mode: str = "cash",
           note: str = "", due_date=None, as_of=None) -> Result:
    """Apply one quick entry. Raises EntryError with an owner-friendly message if it can't."""
    if kind not in KINDS:
        raise EntryError("Unknown entry type.")
    try:
        amount = float(amount)
    except (TypeError, ValueError) as e:
        raise EntryError("Enter the amount as a number.") from e
    if not 0 < amount < 1e10:
        raise EntryError("Enter an amount above zero.")
    d = pd.Timestamp(date).normalize()
    if as_of is not None and d > pd.Timestamp(as_of).normalize():
        raise EntryError(f"The date can't be after {pd.Timestamp(as_of):%d %b %Y}.")
    party = (party or "").strip()[:80]
    note = (note or "").strip()[:200]
    mode = (mode or "cash").lower()
    if mode not in MODES:
        mode = "cash"
    t = tables.copy()
    before_ledger_ids = set(t.ledger["txn_id"])
    undo: dict = {"ledger_added": [], "obligations_added": [], "obligations_before": []}
    settled: list[dict] = []
    unapplied = 0.0

    if kind == "sale":
        who = party or "Walk-in customer"
        eid = _add_ledger(t, d, amount, "in", category or "Sales", who, note or "Sale", mode)
        summary = f"Sale {fmt_inr(amount)} · {who} · {mode.upper()}"
    elif kind == "expense":
        cat = category or "Uncategorised"
        eid = _add_ledger(t, d, amount, "out", cat, party or cat, note or cat, mode)
        summary = f"Spent {fmt_inr(amount)} on {cat.lower()}" + (f" · {party}" if party else "")
    elif kind in ("credit_sale", "bill"):
        if not party:
            raise EntryError("Whose name should this be under?")
        due = pd.Timestamp(due_date).normalize() if due_date else d + pd.Timedelta(days=15)
        if due < d:
            raise EntryError("The due date can't be before the entry date.")
        if kind == "credit_sale":
            eid = _add_obligation(t, "receivable", party, amount, d, due, note or "Udhaar (goods on credit)", category or "Sales")
            summary = f"Udhaar {fmt_inr(amount)} to {party}, due {due:%d %b}"
        else:
            eid = _add_obligation(t, "payable", party, amount, d, due, note or "Supplier bill", category or "Raw materials")
            summary = f"Bill {fmt_inr(amount)} from {party}, due {due:%d %b}"
        undo["obligations_added"].append(eid)
    else:  # payment_in / payment_out
        if not party:
            raise EntryError("Who paid / who did you pay?")
        okind = "receivable" if kind == "payment_in" else "payable"
        settled, unapplied, before, new_ids = _settle(t, okind, party, amount, d)
        undo["obligations_before"] = before
        undo["obligations_added"] = new_ids
        if kind == "payment_in":
            cat = category or "Sales"
            ids = ", ".join(s["item_id"] for s in settled)
            eid = _add_ledger(t, d, amount, "in", cat, party, note or (f"Payment received against {ids}" if ids else "Payment received"), mode)
            summary = f"Received {fmt_inr(amount)} from {party}"
        else:
            first = None
            if settled and t.obligations is not None:
                first = t.obligations.loc[t.obligations["item_id"] == settled[0]["item_id"], "category"].iloc[0]
            cat = category or first or "Uncategorised"
            ids = ", ".join(s["item_id"] for s in settled)
            eid = _add_ledger(t, d, amount, "out", cat, party, note or (f"Payment for {ids}" if ids else "Supplier payment"), mode)
            summary = f"Paid {fmt_inr(amount)} to {party}"
    undo["ledger_added"] = sorted(set(t.ledger["txn_id"]) - before_ledger_ids)
    return Result(t, eid, summary, undo, settled, unapplied)


def undo(tables: Tables, rec: dict) -> Tables:
    """Reverse an entry using its undo record."""
    t = tables.copy()
    if rec.get("ledger_added"):
        t.ledger = t.ledger[~t.ledger["txn_id"].isin(rec["ledger_added"])].reset_index(drop=True)
    if t.obligations is not None:
        o = t.obligations
        if rec.get("obligations_added"):
            o = o[~o["item_id"].isin(rec["obligations_added"])]
        for row in rec.get("obligations_before", []):
            o = o[o["item_id"] != row["item_id"]]
            o = pd.concat([o, pd.DataFrame([row])], ignore_index=True)
        for c in ("issue_date", "due_date", "paid_date"):
            o[c] = pd.to_datetime(o[c])
        o["amount"] = o["amount"].astype(float)
        t.obligations = o.reset_index(drop=True)
    return t
