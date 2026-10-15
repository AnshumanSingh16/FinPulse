"""Monthly spending limits per category, and savings goals."""

from __future__ import annotations

import calendar

import pandas as pd

from finpilot.engine.common import last_full_month, money, prepare_ledger, ts

COST_CLASSES = ("operating", "unclassified_out")


def suggest_budgets(ledger: pd.DataFrame, as_of, months: int = 3) -> dict[str, float]:
    """Average monthly spend per running-cost category over the last full months, rounded up to ₹500."""
    df = prepare_ledger(ledger)
    _, end = last_full_month(as_of)
    start = (end - pd.DateOffset(months=months - 1)).replace(day=1)
    w = df[(df["date"] >= start) & (df["date"] <= end) & (df["direction"] == "out") & df["cls"].isin(COST_CLASSES)]
    out = {}
    for cat, v in w.groupby("category")["amount"].sum().items():
        avg = v / months
        if avg >= 500:
            out[cat] = float(-(-avg // 500) * 500)
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def budget_status(ledger: pd.DataFrame, budgets: dict[str, float], as_of) -> dict:
    """Spent this month so far vs each limit, with the month-end pace at the current rate."""
    a = ts(as_of)
    start = a.replace(day=1)
    days_in = calendar.monthrange(a.year, a.month)[1]
    elapsed = a.day
    df = prepare_ledger(ledger) if len(ledger) else None
    rows = []
    for cat, limit in budgets.items():
        spent = 0.0
        if df is not None:
            m = df[(df["date"] >= start) & (df["date"] <= a) & (df["direction"] == "out") & (df["category"] == cat)]
            spent = money(m["amount"].sum())
        pace = money(spent / elapsed * days_in) if elapsed else spent
        pct = round(spent / limit * 100, 1) if limit else 0
        state = "over" if spent > limit else "near" if pct >= 80 or pace > limit else "ok"
        rows.append({"category": cat, "limit": money(limit), "spent": spent, "left": money(limit - spent), "pct": pct, "pace": pace, "state": state})
    rows.sort(key=lambda r: -r["pct"])
    total_limit = money(sum(budgets.values()))
    total_spent = money(sum(r["spent"] for r in rows))
    return {"month": a.strftime("%B %Y"), "days_left": days_in - elapsed, "days_in_month": days_in, "rows": rows,
            "total_limit": total_limit, "total_spent": total_spent, "over": [r["category"] for r in rows if r["state"] == "over"]}


def goal_plan(goal: dict, as_of) -> dict:
    """Monthly saving needed to reach a goal by its date."""
    a = ts(as_of)
    left = max(float(goal["target"]) - float(goal["saved"]), 0.0)
    pct = round(min(float(goal["saved"]) / float(goal["target"]) * 100, 100), 1) if goal["target"] else 0
    per_month = None
    months_left = None
    if goal.get("target_date"):
        d = ts(goal["target_date"])
        months_left = max((d.year - a.year) * 12 + d.month - a.month, 0)
        per_month = money(left / months_left) if months_left else money(left)
    return goal | {"left": money(left), "pct": pct, "done": left <= 0, "per_month": per_month, "months_left": months_left}
