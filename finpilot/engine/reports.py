"""Shareable reports: a monthly summary for your CA, and a loan-readiness summary for a bank."""

from __future__ import annotations

import pandas as pd

from finpilot.engine.calendar_gst import gst_estimate
from finpilot.engine.cash import cash_position, obligations_status
from finpilot.engine.common import last_full_month, money, prepare_ledger, ts
from finpilot.engine.health import obligations_as_of
from finpilot.engine.summary import financial_summary


def _balance_on(ledger, balances, d):
    p = cash_position(ledger, balances, d)
    return p["cash_balance"] if p["status"] == "ok" else None


def monthly(ledger, balances, obligations, as_of, year: int, month: int, gst_rates=(5.0, 5.0)) -> dict:
    start = pd.Timestamp(year=year, month=month, day=1)
    end = min((start + pd.offsets.MonthEnd(0)).normalize(), ts(as_of))
    s = financial_summary(ledger, start, end)
    if s["status"] != "ok":
        return {"status": "insufficient_data", "message": s["message"]}
    df = prepare_ledger(ledger)
    w = df[(df["date"] >= start) & (df["date"] <= end)]
    sales = w[w["cls"] == "revenue"]
    top_customers = [{"name": n, "amount": money(v)} for n, v in sales.groupby("counterparty")["amount"].sum().sort_values(ascending=False).head(5).items()]
    top_suppliers = [{"name": n, "amount": money(v)} for n, v in w[w["direction"] == "out"].groupby("counterparty")["amount"].sum().sort_values(ascending=False).head(5).items()]
    obl = obligations_status(obligations_as_of(obligations, end), end)
    return {
        "status": "ok",
        "label": start.strftime("%B %Y"),
        "period": [str(start.date()), str(end.date())],
        "summary": {k: s[k] for k in ("revenue", "operating_expenses", "estimated_operating_profit", "estimated_margin_pct", "total_inflows", "total_outflows", "net_cash_movement")},
        "other_flows": s["other_flows"],
        "expenses_by_category": s["expenses_by_category"],
        "opening_balance": _balance_on(ledger, balances, start - pd.Timedelta(days=1)),
        "closing_balance": _balance_on(ledger, balances, end),
        "top_customers": top_customers,
        "top_suppliers": top_suppliers,
        "receivables": obl.get("receivables") if obl["status"] == "ok" else None,
        "payables": obl.get("payables") if obl["status"] == "ok" else None,
        "gst": gst_estimate(ledger, start, end, *gst_rates),
        "transactions": int(len(w)),
        "evidence": s["evidence"],
    }


def loan_readiness(ledger, balances, obligations, as_of) -> dict:
    a = ts(as_of)
    _, end = last_full_month(a)
    start = (end - pd.DateOffset(months=5)).replace(day=1)
    s = financial_summary(ledger, start, end)
    if s["status"] != "ok":
        return {"status": "insufficient_data", "message": "Needs at least a few months of transactions."}
    n = max(len(s["monthly"]), 1)
    avg_sales = s["revenue"] / n
    avg_profit = s["estimated_operating_profit"] / n
    emis = s["other_flows"]["loan_repayments"] / n
    months = s["monthly"]
    first_half = sum(m["revenue"] for m in months[: n // 2]) or None
    second_half = sum(m["revenue"] for m in months[n // 2:])
    growth = round((second_half - first_half) / first_half * 100, 1) if first_half else None
    # balance on each month-end
    ends = [(pd.Timestamp(m["month"] + "-01") + pd.offsets.MonthEnd(0)).normalize() for m in months]
    bals = [b for b in (_balance_on(ledger, balances, d) for d in ends) if b is not None]
    obl = obligations_status(obligations, a)
    overdue_pct = None
    if obl["status"] == "ok":
        r = obl["receivables"]
        tot = r["pending_not_due"] + r["overdue"]
        overdue_pct = round(r["overdue"] / tot * 100, 1) if tot else 0.0
    cover = round(avg_profit / emis, 2) if emis else None
    checks = [
        {"key": "history", "label": "Months of records", "value": n, "ok": n >= 6, "target": "6 or more"},
        {"key": "profit", "label": "Average monthly profit (estimate)", "value": money(avg_profit), "ok": avg_profit > 0, "target": "Above zero"},
        {"key": "cover", "label": "Profit ÷ existing EMIs", "value": cover, "ok": cover is None or cover >= 1.25, "target": "1.25 or more"},
        {"key": "balance", "label": "Lowest month-end bank balance", "value": min(bals) if bals else None, "ok": bool(bals) and min(bals) > 0, "target": "Never negative"},
        {"key": "growth", "label": "Sales trend (last 3 vs first 3 months)", "value": growth, "ok": growth is None or growth >= -10, "target": "Not falling over 10%"},
        {"key": "collections", "label": "Customer dues overdue", "value": overdue_pct, "ok": overdue_pct is None or overdue_pct <= 25, "target": "25% or less"},
    ]
    passed = sum(c["ok"] for c in checks)
    level = "strong" if passed >= 6 else "fair" if passed >= 4 else "weak"
    return {
        "status": "ok",
        "period": [str(start.date()), str(end.date())],
        "avg_monthly_sales": money(avg_sales),
        "avg_monthly_profit": money(avg_profit),
        "avg_monthly_emi": money(emis),
        "avg_month_end_balance": money(sum(bals) / len(bals)) if bals else None,
        "sales_growth_pct": growth,
        "checks": checks,
        "passed": passed,
        "level": level,
        "monthly": [{"month": m["month"], "sales": m["revenue"], "profit": m["estimated_operating_profit"]} for m in months],
        "documents": ["Last 12 months of bank statements", "GST returns (GSTR-3B) for the last 12 months", "Income tax returns for 2 years",
                      "Udyam registration", "PAN and Aadhaar / KYC of the owner", "Business address proof"],
        "evidence": s["evidence"],
    }
