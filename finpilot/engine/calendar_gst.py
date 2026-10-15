"""
Money calendar and GST estimate.

The calendar shows, for each day of a month: money that actually moved, invoices and bills due,
regular payments expected from past habits (e.g. rent around the 5th), and typical statutory due
dates. Statutory dates are the common defaults — they can change (extensions, QRMP), so they are
labelled "typical" and the owner is told to confirm on the GST portal.

The GST estimate assumes sales receipts include GST at one rate and that purchases in goods-and-
services categories carry input GST at one rate. It is a set-aside guide, not a return.
"""

from __future__ import annotations

import calendar as cal

import pandas as pd

from finpilot.data.schema import Evidence
from finpilot.engine.common import money, prepare_ledger, ts

ITC_CATEGORIES = {"raw materials", "packaging", "logistics", "software", "repairs & maintenance", "office supplies", "purchases",
                  "professional fees", "marketing", "utilities", "electricity", "equipment", "machinery", "rent"}
REGULAR = ("rent", "salaries", "loan emi", "software", "electricity", "utilities", "insurance")


def statutory_dates(year: int, month: int, filing: str = "monthly", registered: bool = True) -> list[dict]:
    out = [{"day": 7, "kind": "tax", "title": "TDS deposit for last month", "note": "If you deduct TDS (e.g. on rent or contractor payments)."}]
    if registered:
        quarter_next = month in (1, 4, 7, 10)
        if filing == "qrmp":
            if quarter_next:
                out.append({"day": 13, "kind": "tax", "title": "GSTR-1 (quarterly)", "note": "Sales return for last quarter."})
                out.append({"day": 22, "kind": "tax", "title": "GSTR-3B (quarterly) + GST payment", "note": "22nd or 24th depending on your state."})
            else:
                out.append({"day": 25, "kind": "tax", "title": "GST payment (PMT-06)", "note": "Monthly payment under QRMP."})
        else:
            out.append({"day": 11, "kind": "tax", "title": "GSTR-1", "note": "Last month's sales invoices."})
            out.append({"day": 20, "kind": "tax", "title": "GSTR-3B + GST payment", "note": "Pay last month's GST."})
    if month in (6, 9, 12, 3):
        out.append({"day": 15, "kind": "tax", "title": "Advance income tax instalment", "note": "If your yearly tax is over ₹10,000."})
    for o in out:
        o["date"] = str(pd.Timestamp(year=year, month=month, day=o["day"]).date())
        o["typical"] = True
    return out


def regular_days(ledger: pd.DataFrame, as_of, min_months: int = 3) -> list[dict]:
    """Payments that recur monthly on a similar day (rent on the 5th, salaries on the 1st...)."""
    df = prepare_ledger(ledger)
    df = df[(df["direction"] == "out") & (df["date"] <= ts(as_of)) & (df["date"] > ts(as_of) - pd.DateOffset(months=6))]
    out = []
    for cat, g in df.groupby("category"):
        if str(cat).lower() not in REGULAR:
            continue
        months = g["date"].dt.to_period("M").nunique()
        if months < min_months:
            continue
        typical_day = int(g["date"].dt.day.median())
        amount = float(g.groupby(g["date"].dt.to_period("M"))["amount"].sum().median())
        out.append({"category": cat, "day": typical_day, "amount": money(amount), "party": g["counterparty"].mode().iloc[0]})
    return out


def month_calendar(ledger: pd.DataFrame, obligations, as_of, year: int, month: int, filing: str = "monthly", registered: bool = True) -> dict:
    a = ts(as_of)
    first = pd.Timestamp(year=year, month=month, day=1)
    n = cal.monthrange(year, month)[1]
    last = first + pd.Timedelta(days=n - 1)
    days = {d: {"date": str((first + pd.Timedelta(days=d - 1)).date()), "day": d, "in": 0.0, "out": 0.0, "events": []} for d in range(1, n + 1)}
    if len(ledger):
        df = prepare_ledger(ledger)
        m = df[(df["date"] >= first) & (df["date"] <= min(last, a))]
        for d, g in m.groupby(m["date"].dt.day):
            days[d]["in"] = money(g.loc[g["direction"] == "in", "amount"].sum())
            days[d]["out"] = money(g.loc[g["direction"] == "out", "amount"].sum())
    scheduled_cats = set()
    if obligations is not None and len(obligations):
        o = obligations.copy()
        o["due_date"] = pd.to_datetime(o["due_date"])
        pend = o[(o["status"] == "pending") & (o["due_date"] >= first) & (o["due_date"] <= last)]
        for r in pend.itertuples():
            days[r.due_date.day]["events"].append({"kind": "receivable" if r.kind == "receivable" else "payable", "title": r.counterparty,
                                                    "detail": r.description, "amount": float(r.amount), "id": r.item_id,
                                                    "overdue": bool(r.due_date < a)})
            if r.kind == "payable":
                scheduled_cats.add(str(r.category).lower())
    if last > a:  # expected regular payments for days still ahead
        for r in regular_days(ledger, a) if len(ledger) else []:
            dd = min(r["day"], n)
            d = first + pd.Timedelta(days=dd - 1)
            if d > a and str(r["category"]).lower() not in scheduled_cats:
                days[dd]["events"].append({"kind": "expected", "title": r["category"], "detail": f"Usually paid to {r['party']} around day {dd}",
                                           "amount": r["amount"], "id": None, "overdue": False})
    for s in statutory_dates(year, month, filing, registered):
        days[s["day"]]["events"].append({"kind": "tax", "title": s["title"], "detail": s["note"], "amount": None, "id": None, "overdue": False, "typical": True})
    lst = list(days.values())
    return {
        "year": year, "month": month, "label": first.strftime("%B %Y"), "first_weekday": first.weekday(), "days": lst,
        "money_in": money(sum(d["in"] for d in lst)), "money_out": money(sum(d["out"] for d in lst)),
        "due_in": money(sum(e["amount"] or 0 for d in lst for e in d["events"] if e["kind"] == "receivable")),
        "due_out": money(sum(e["amount"] or 0 for d in lst for e in d["events"] if e["kind"] in ("payable", "expected"))),
    }


def gst_estimate(ledger: pd.DataFrame, start, end, rate_sales: float, rate_purchases: float) -> dict:
    df = prepare_ledger(ledger)
    w = df[(df["date"] >= ts(start)) & (df["date"] <= ts(end))]
    sales = float(w.loc[(w["direction"] == "in") & (w["cls"] == "revenue"), "amount"].sum())
    buys = w[(w["direction"] == "out") & w["category"].str.lower().isin(ITC_CATEGORIES)]
    purchases = float(buys["amount"].sum())
    out_tax = sales * rate_sales / (100 + rate_sales)
    in_tax = purchases * rate_purchases / (100 + rate_purchases)
    paid = float(w.loc[(w["direction"] == "out") & (w["category"].str.lower() == "gst payment"), "amount"].sum())
    return {
        "period": [str(ts(start).date()), str(ts(end).date())],
        "sales_incl_gst": money(sales),
        "output_gst": money(out_tax),
        "purchases_incl_gst": money(purchases),
        "input_credit": money(in_tax),
        "estimated_payable": money(max(out_tax - in_tax, 0.0)),
        "gst_paid_in_period": money(paid),
        "evidence": Evidence(
            method=f"Output GST = sales received × {rate_sales:g}/(100+{rate_sales:g}). Input credit = purchases in goods & services categories × "
                   f"{rate_purchases:g}/(100+{rate_purchases:g}). Estimated payable = output − input credit (not below zero).",
            assumptions=(f"All sales include GST at {rate_sales:g}%.", f"Purchases in {', '.join(sorted(ITC_CATEGORIES))} carry {rate_purchases:g}% GST and are eligible for credit."),
            limitations=("An estimate to help you set money aside — not a GST return. Mixed rates, exempt items, reverse charge and "
                         "unclaimed credits are not handled. Your CA's figures take precedence.",),
            record_ids=tuple(w["txn_id"]),
            period=(str(ts(start).date()), str(ts(end).date())),
        ).to_dict(),
    }
