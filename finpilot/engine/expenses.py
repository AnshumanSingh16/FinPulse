"""Expense comparison between periods, possible duplicates, and unusual transactions."""

from __future__ import annotations

import pandas as pd

from finpilot.data.schema import Evidence
from finpilot.engine.common import in_period, last_full_month, money, prepare_ledger, ts
from finpilot.engine.summary import OPEX_CLASSES


def _opex(df: pd.DataFrame) -> pd.DataFrame:
    return df[(df["direction"] == "out") & df["cls"].isin(OPEX_CLASSES)]


def default_periods(as_of, months: int = 1):
    """The last `months` full months vs the `months` before them."""
    _, b_end = last_full_month(as_of)
    b_start = (b_end - pd.DateOffset(months=months - 1)).replace(day=1)
    a_end = b_start - pd.Timedelta(days=1)
    a_start = (a_end - pd.DateOffset(months=months - 1)).replace(day=1)
    return (a_start, a_end), (b_start, b_end)


def compare_expenses(ledger: pd.DataFrame, period_a, period_b, top_n: int = 3) -> dict:
    """Operating expenses by category: period A (earlier) vs period B (later)."""
    df = prepare_ledger(ledger)
    a = _opex(in_period(df, *period_a))
    b = _opex(in_period(df, *period_b))
    if a.empty and b.empty:
        return {
            "status": "insufficient_data",
            "message": "No operating expenses in either period.",
            "evidence": Evidence(method="Nothing to compare.").to_dict(),
        }
    ta = a.groupby("category")["amount"].sum()
    tb = b.groupby("category")["amount"].sum()
    cats = sorted(set(ta.index) | set(tb.index))
    rows = []
    for c in cats:
        va, vb = float(ta.get(c, 0.0)), float(tb.get(c, 0.0))
        top = b[b["category"] == c].nlargest(top_n, "amount")
        rows.append(
            {
                "category": c,
                "period_a": money(va),
                "period_b": money(vb),
                "change": money(vb - va),
                "change_pct": money(100 * (vb - va) / va) if va else None,
                "largest_in_b": [
                    {"txn_id": r.txn_id, "date": str(r.date.date()), "description": r.description, "amount": money(r.amount)}
                    for r in top.itertuples()
                ],
                "count_a": int((a["category"] == c).sum()),
                "count_b": int((b["category"] == c).sum()),
            }
        )
    rows.sort(key=lambda r: -abs(r["change"]))
    total_a, total_b = float(a["amount"].sum()), float(b["amount"].sum())
    days_a = (ts(period_a[1]) - ts(period_a[0])).days + 1
    days_b = (ts(period_b[1]) - ts(period_b[0])).days + 1
    limitations = ["Compares recorded payments only; bills received but unpaid are not included."]
    if days_a != days_b:
        limitations.append(f"The periods have different lengths ({days_a} vs {days_b} days).")
    return {
        "status": "ok",
        "period_a": {"start": str(ts(period_a[0]).date()), "end": str(ts(period_a[1]).date())},
        "period_b": {"start": str(ts(period_b[0]).date()), "end": str(ts(period_b[1]).date())},
        "total_a": money(total_a),
        "total_b": money(total_b),
        "total_change": money(total_b - total_a),
        "total_change_pct": money(100 * (total_b - total_a) / total_a) if total_a else None,
        "by_category": rows,
        "evidence": Evidence(
            method="Sum of operating-expense outflows per category in each period; change = B − A.",
            limitations=tuple(limitations),
            record_ids=tuple(a["txn_id"]) + tuple(b["txn_id"]),
            period=(str(ts(period_a[0]).date()), str(ts(period_b[1]).date())),
        ).to_dict(),
    }


def find_duplicates(df: pd.DataFrame, keys=("date", "amount", "counterparty", "category", "direction")) -> list[list[str]]:
    """Groups of rows that agree on every key: likely the same payment recorded twice."""
    keys = [k for k in keys if k in df.columns]
    id_col = "txn_id" if "txn_id" in df.columns else None
    groups = []
    for _, g in df.groupby(keys, dropna=False):
        if len(g) > 1:
            groups.append([str(x) for x in (g[id_col] if id_col else g.index)])
    return groups


def unusual_transactions(
    ledger: pd.DataFrame,
    as_of,
    lookback_days: int = 90,
    min_history: int = 4,
    z_threshold: float = 3.5,
    rare_large_amount: float = 50_000,
) -> dict:
    """
    Flags in the last `lookback_days` up to as_of:
      * possible duplicates (same date, amount, counterparty, category, direction)
      * outliers: an expense far above its category's history (robust z-score on median/MAD, and at
        least 1.5× the median)
      * large payments in a category with too little history to judge
    """
    df = prepare_ledger(ledger)
    end = ts(as_of)
    start = end - pd.Timedelta(days=lookback_days - 1)
    window = in_period(df, start, end)
    flags = []

    for group in find_duplicates(window):
        rows = window[window["txn_id"].isin(group)]
        r = rows.iloc[0]
        flags.append(
            {
                "type": "possible_duplicate",
                "txn_ids": group,
                "date": str(r.date.date()),
                "category": r.category,
                "counterparty": r.counterparty,
                "amount": money(r.amount),
                "reason": f"{len(group)} identical {r.direction}flows on the same day to/from the same party.",
                "excess": money(r.amount * (len(group) - 1)),
            }
        )

    exp = _opex(window)
    history_all = _opex(df)
    for r in exp.itertuples():
        hist = history_all[(history_all["category"] == r.category) & (history_all["date"] < r.date)]["amount"]
        if len(hist) < min_history:
            if r.amount >= rare_large_amount:
                flags.append(
                    {
                        "type": "rare_large_payment",
                        "txn_ids": [r.txn_id],
                        "date": str(r.date.date()),
                        "category": r.category,
                        "counterparty": r.counterparty,
                        "amount": money(r.amount),
                        "reason": f"Large payment in a category with only {len(hist)} earlier payment(s) to compare with.",
                        "excess": None,
                    }
                )
            continue
        med = float(hist.median())
        mad = float((hist - med).abs().median())
        scale = mad if mad > 0 else max(1.0, 0.05 * med)
        z = 0.6745 * (r.amount - med) / scale
        if z > z_threshold and r.amount >= 1.5 * med:
            flags.append(
                {
                    "type": "outlier",
                    "txn_ids": [r.txn_id],
                    "date": str(r.date.date()),
                    "category": r.category,
                    "counterparty": r.counterparty,
                    "amount": money(r.amount),
                    "reason": f"{r.amount / med:.1f}× the usual {r.category.lower()} payment (median {med:,.0f} over {len(hist)} earlier payments).",
                    "excess": money(r.amount - med),
                    "robust_z": round(z, 1),
                }
            )
    flags.sort(key=lambda f: f["date"], reverse=True)
    return {
        "status": "ok",
        "window": {"start": str(start.date()), "end": str(end.date())},
        "flags": flags,
        "evidence": Evidence(
            method=(
                "Duplicates: rows identical in date, amount, counterparty, category and direction. "
                f"Outliers: robust z-score (0.6745 × (amount − median) / MAD) above {z_threshold} against "
                f"the category's earlier payments, and at least 1.5× the median; categories with fewer than "
                f"{min_history} earlier payments are flagged only for payments of {rare_large_amount:,.0f} or more."
            ),
            limitations=(
                "A flag is a prompt to check, not a finding of error: duplicates may be two genuine payments.",
            ),
            record_ids=tuple(i for f in flags for i in f["txn_ids"]),
            period=(str(start.date()), str(end.date())),
        ).to_dict(),
    }
