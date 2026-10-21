"""
"Why are my sales less this month?" — an investigation, not a total.

Sales received this month are compared with the same span of last month and the change is split into causes,
each only as far as the records support it:

* by customer: who paid less, who stopped, who is new (the per-customer changes add up exactly to the total change);
* pooled takings (counter, POS, UPI settlements) are kept apart — the bank can't tell how many orders are inside them;
* number of payments × average payment, for named customers (orders effect + size effect = their change, exactly);
* delayed money: invoices due in the period that haven't arrived — a late payment, not lost business;
* history: how this month compares with recent months and, if the books go back far enough, the same month last year.

What the records can't show (which products, prices, footfall) is listed as not verified, with what to upload to check it.
Every amount here is Python arithmetic on the ledger and the invoices; nothing is estimated by a language model.
"""

from __future__ import annotations

import re

import pandas as pd

from finpilot.data.schema import Evidence
from finpilot.engine.common import fmt_inr, money, prepare_ledger, ts

POOLED = re.compile(r"settlement|\bpos\b|counter|walk.?in|cash sales?|upi|swiggy|zomato|delivery app|aggregator|paytm|phonepe|gpay|razorpay|cashfree", re.I)
MIN_HISTORY_MONTHS = 3


def _spans(as_of: pd.Timestamp) -> tuple[tuple[pd.Timestamp, pd.Timestamp], tuple[pd.Timestamp, pd.Timestamp]]:
    """This month to date, and the same number of days at the start of last month (a fair like-for-like span)."""
    cur_start = as_of.replace(day=1)
    prev_start = (cur_start - pd.Timedelta(days=1)).replace(day=1)
    prev_end_month = cur_start - pd.Timedelta(days=1)
    if as_of == as_of + pd.offsets.MonthEnd(0):
        return (cur_start, as_of), (prev_start, prev_end_month)
    prev_end = min(prev_start + pd.Timedelta(days=as_of.day - 1), prev_end_month)
    return (cur_start, as_of), (prev_start, prev_end)


def _sales(ledger: pd.DataFrame) -> pd.DataFrame:
    df = prepare_ledger(ledger)
    s = df[(df["cls"] == "revenue") & (df["direction"] == "in")].copy()
    s["counterparty"] = s["counterparty"].fillna("").astype(str).str.strip()
    s["pooled"] = (s["counterparty"] == "") | s["counterparty"].str.contains(POOLED) | s["description"].astype(str).str.contains(POOLED)
    return s


def _between(df: pd.DataFrame, span) -> pd.DataFrame:
    return df[(df["date"] >= span[0]) & (df["date"] <= span[1])]


def sales_change(ledger: pd.DataFrame, obligations: pd.DataFrame | None, as_of, start=None, end=None) -> dict:
    as_of = ts(as_of)
    if ledger is None or not len(ledger):
        return {"status": "no_data", "message": "There are no transactions yet. Upload a bank statement or add sales to investigate them."}
    s = _sales(ledger)
    if not len(s):
        return {"status": "no_data", "message": "No sales were found in your records (no money in under a sales category)."}
    if start is not None and end is not None:
        cur = (ts(start), ts(end))
        days = (cur[1] - cur[0]).days
        prev = (cur[0] - pd.Timedelta(days=days + 1), cur[0] - pd.Timedelta(days=1))
    else:
        cur, prev = _spans(as_of)
    a, b = _between(s, cur), _between(s, prev)
    total_cur, total_prev = money(a["amount"].sum()), money(b["amount"].sum())
    change = money(total_cur - total_prev)

    # --- by customer (named) and pooled takings; these add up exactly to the change
    named_a, named_b = a[~a["pooled"]], b[~b["pooled"]]
    by = pd.DataFrame({"cur": named_a.groupby("counterparty")["amount"].sum(), "prev": named_b.groupby("counterparty")["amount"].sum()}).fillna(0.0)
    by["change"] = by["cur"] - by["prev"]
    pend = _pending_receivables(obligations, as_of)
    customers = []
    for party, r in by.sort_values("change").iterrows():
        if abs(r["change"]) < 0.5:
            continue
        kind = "stopped" if r["cur"] == 0 else "new" if r["prev"] == 0 else "less" if r["change"] < 0 else "more"
        owed = pend[pend["counterparty"] == party] if len(pend) else pend
        due_in_span = owed[(owed["due_date"] <= cur[1])] if len(owed) else owed
        customers.append({
            "party": party, "prev": money(r["prev"]), "cur": money(r["cur"]), "change": money(r["change"]), "kind": kind,
            "payments_prev": int((named_b["counterparty"] == party).sum()), "payments_cur": int((named_a["counterparty"] == party).sum()),
            "unpaid_due": money(due_in_span["amount"].sum()) if len(due_in_span) else 0.0,
            "unpaid_items": list(due_in_span["item_id"]) if len(due_in_span) else [],
            "record_ids": list(named_a.loc[named_a["counterparty"] == party, "txn_id"]) + list(named_b.loc[named_b["counterparty"] == party, "txn_id"]),
        })
    pooled_cur, pooled_prev = money(a.loc[a["pooled"], "amount"].sum()), money(b.loc[b["pooled"], "amount"].sum())
    pooled = None
    if pooled_cur or pooled_prev:
        pa, pb = a[a["pooled"]], b[b["pooled"]]
        pooled = {"prev": pooled_prev, "cur": pooled_cur, "change": money(pooled_cur - pooled_prev),
                  "parties": sorted(set(pa["counterparty"]) | set(pb["counterparty"]) - {""}) or ["(no name)"],
                  "days_prev": int(pb["date"].nunique()), "days_cur": int(pa["date"].nunique()),
                  "per_day_prev": money(pooled_prev / max(pb["date"].nunique(), 1)), "per_day_cur": money(pooled_cur / max(pa["date"].nunique(), 1)),
                  "record_ids": list(pa["txn_id"]) + list(pb["txn_id"])}

    # --- named customers: number of payments × average payment (orders effect + size effect = their change)
    mix = None
    n0, n1 = len(named_b), len(named_a)
    if n0 and n1:
        a0, a1 = named_b["amount"].mean(), named_a["amount"].mean()
        mix = {"payments_prev": n0, "payments_cur": n1, "avg_prev": money(a0), "avg_cur": money(a1),
               "customers_prev": int(named_b["counterparty"].nunique()), "customers_cur": int(named_a["counterparty"].nunique()),
               "count_effect": money((n1 - n0) * a0), "size_effect": money((a1 - a0) * n1)}

    # --- delayed money: invoices due by the end of the span that haven't arrived (not lost business)
    late = []
    if len(pend):
        due = pend[pend["due_date"] <= cur[1]]
        for _, r in due.sort_values("due_date").iterrows():
            late.append({"item_id": r["item_id"], "party": r["counterparty"], "amount": money(r["amount"]), "due_date": str(r["due_date"].date()),
                         "days_late": int((as_of - r["due_date"]).days)})
    late_total = money(sum(x["amount"] for x in late))
    late_in_span = money(sum(x["amount"] for x in late if pd.Timestamp(x["due_date"]) >= cur[0]))

    # --- history: recent months and the same month last year
    months = s.assign(m=s["date"].dt.to_period("M")).groupby("m")["amount"].sum()
    this_m = cur[0].to_period("M")
    full_before = months[months.index < this_m]
    history = [{"month": str(k), "total": money(v)} for k, v in full_before.tail(6).items()]
    avg6 = money(full_before.tail(6).mean()) if len(full_before) else None
    compared = full_before.tail(11)
    lower_than = int((compared > total_cur).sum())
    ly = this_m - 12
    seasonal = {"available": ly in months.index and s["date"].min() <= ly.start_time, "month": str(ly)}
    if seasonal["available"]:
        seasonal |= {"total": money(months[ly]), "change": money(total_cur - months[ly])}
    partial = cur[1] < cur[0] + pd.offsets.MonthEnd(0)

    # --- what the records can't tell, and what would let FinPilot check it
    unverified = ["Which products or services sold less — bank records show payments, not items. Upload item-wise sales from your billing app (Excel/CSV) to check."]
    if pooled:
        unverified.append(f"How many orders are inside pooled takings ({', '.join(pooled['parties'][:3])}) — they arrive as one payment per settlement, so fewer or smaller orders can't be told apart.")
    if not seasonal["available"]:
        unverified.append(f"Whether this is seasonal — the books start {s['date'].min():%b %Y}, so there's no {pd.Period(ly).strftime('%B %Y')} to compare with.")
    unverified.append("Prices you charged, discounts, footfall and returns — none of these are in a bank statement.")
    ask_for = []
    if len(full_before) < MIN_HISTORY_MONTHS:
        ask_for.append("At least three months of bank statements, so a normal month can be told from an unusual one.")
    if not len(named_a) and not len(named_b):
        ask_for.append("Customer-wise sales (invoices or a sales register) — every sale here is pooled, so the drop can't be traced to customers.")
    ask_for.append("Item-wise sales from your billing app, to see which products moved.")

    drivers = _drivers(customers, pooled, late_in_span)
    rec = [r for c in customers for r in c["record_ids"]] + (pooled["record_ids"] if pooled else []) + [x["item_id"] for x in late]
    return {
        "status": "ok",
        "period": {"current": [str(cur[0].date()), str(cur[1].date())], "previous": [str(prev[0].date()), str(prev[1].date())], "partial_month": partial},
        "sales": {"current": total_cur, "previous": total_prev, "change": change, "change_pct": money(change / total_prev * 100) if total_prev else None},
        "drivers": drivers,
        "customers": customers,
        "pooled": pooled,
        "mix": mix,
        "late_payments": {"total": late_total, "due_this_period": late_in_span, "items": late[:12]},
        "history": {"months": history, "average_6m": avg6, "months_compared": int(len(compared)), "months_higher": lower_than},
        "seasonal": seasonal,
        "unverified": unverified,
        "ask_for": ask_for,
        "evidence": Evidence(
            method=("Sales = money in under sales categories. Change = this period − the same span of last month. "
                    "Per customer: change = their payments this period − last period; these plus the change in pooled takings add up to the total change. "
                    "Payments × average payment: count effect = (payments now − before) × average before; size effect = (average now − before) × payments now; "
                    "together they equal the named customers' change. Delayed money = pending invoices whose due date has passed."),
            assumptions=("A payment from a named customer is one order (several orders paid together would count as one).",
                         "Pooled takings (counter, POS, UPI or app settlements) are treated as one stream of sales.",
                         "An invoice still marked pending is unpaid as of today."),
            limitations=("Cash basis: a sale counts when the money arrives, not when the invoice is raised.",),
            record_ids=tuple(rec),
            period=(str(cur[0].date()), str(cur[1].date())),
            unverified=tuple(unverified),
        ).to_dict() | {"formula": _formula(total_cur, total_prev, change, drivers, mix, late_in_span)},
    }


def _formula(cur, prev, change, drivers, mix, late) -> list[str]:
    out = [f"Sales this period {fmt_inr(cur)} − last period {fmt_inr(prev)} = {fmt_inr(change)}"]
    parts = [d for d in drivers if not d.get("overlay")]
    if parts:
        out.append("By cause: " + " ".join(f"{'+' if d['amount'] >= 0 else '−'} {fmt_inr(abs(d['amount']))} ({d['label'].lower()})" for d in parts)
                   + f" = {fmt_inr(sum(d['amount'] for d in parts))}")
    if mix:
        out.append(f"Payments: ({mix['payments_cur']} − {mix['payments_prev']}) × {fmt_inr(mix['avg_prev'])} = {fmt_inr(mix['count_effect'])};"
                   f" average: ({fmt_inr(mix['avg_cur'])} − {fmt_inr(mix['avg_prev'])}) × {mix['payments_cur']} = {fmt_inr(mix['size_effect'])}")
    if late:
        out.append(f"Invoices due this period not yet arrived: {fmt_inr(late)}")
    return out


def _pending_receivables(obligations, as_of) -> pd.DataFrame:
    if obligations is None or not len(obligations):
        return pd.DataFrame(columns=["item_id", "counterparty", "amount", "due_date"])
    o = obligations[(obligations["kind"] == "receivable") & (obligations["status"] == "pending")].copy()
    o["due_date"] = pd.to_datetime(o["due_date"]).dt.normalize()
    return o[o["due_date"] <= as_of]


def _drivers(customers: list[dict], pooled: dict | None, late_in_span: float) -> list[dict]:
    """The change, grouped into plain causes. The groups add up to the total change (late money is an overlay, not a group)."""
    groups = {"stopped": "Customers who didn't pay this time", "less": "Customers who paid less", "more": "Customers who paid more", "new": "New customers"}
    out = []
    for k, label in groups.items():
        rows = [c for c in customers if c["kind"] == k]
        if rows:
            out.append({"key": k, "label": label, "amount": money(sum(c["change"] for c in rows)), "parties": [c["party"] for c in rows]})
    if pooled and abs(pooled["change"]) >= 0.5:
        out.append({"key": "pooled", "label": "Counter / app takings", "amount": pooled["change"], "parties": pooled["parties"]})
    out.sort(key=lambda d: d["amount"])
    if late_in_span:
        out.append({"key": "late", "label": "Invoices due this period that haven't arrived", "amount": -late_in_span, "overlay": True, "parties": []})
    return out
