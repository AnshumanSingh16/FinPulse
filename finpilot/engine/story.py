"""The weekly money story: what happened in the last 7 days, compared with the 7 before."""

from __future__ import annotations

import pandas as pd

from finpilot.data.schema import classify
from finpilot.engine.common import money, prepare_ledger, ts


def _window(df: pd.DataFrame, start, end) -> pd.DataFrame:
    return df[(df["date"] >= start) & (df["date"] <= end)]


def weekly_story(ledger: pd.DataFrame, obligations, as_of, days: int = 7) -> dict:
    a = ts(as_of)
    start = a - pd.Timedelta(days=days - 1)
    p_end = start - pd.Timedelta(days=1)
    p_start = p_end - pd.Timedelta(days=days - 1)
    df = prepare_ledger(ledger) if len(ledger) else ledger
    if not len(df):
        return {"status": "empty", "period": [str(start.date()), str(a.date())]}
    w, pw = _window(df, start, a), _window(df, p_start, p_end)

    def totals(x):
        sales = x[x["cls"] == "revenue"]
        costs = x[x["cls"].isin(["operating", "unclassified_out"])]
        return {"money_in": money(x.loc[x["direction"] == "in", "amount"].sum()), "money_out": money(x.loc[x["direction"] == "out", "amount"].sum()),
                "sales": money(sales["amount"].sum()), "costs": money(costs["amount"].sum()), "count": int(len(x))}

    this, prev = totals(w), totals(pw)
    sales = w[w["cls"] == "revenue"]
    best_day = None
    if len(sales):
        by_day = sales.groupby("date")["amount"].sum()
        d = by_day.idxmax()
        best_day = {"date": str(d.date()), "weekday": d.strftime("%A"), "amount": money(by_day.max())}
    top_customer = None
    if len(sales):
        bc = sales.groupby("counterparty")["amount"].sum().sort_values(ascending=False)
        top_customer = {"name": bc.index[0], "amount": money(bc.iloc[0])}
    out = w[w["direction"] == "out"]
    biggest = None
    if len(out):
        r = out.loc[out["amount"].idxmax()]
        biggest = {"what": r["description"], "party": r["counterparty"], "category": r["category"], "amount": money(r["amount"]), "date": str(r["date"].date()), "id": r["txn_id"]}
    cats = out[out["cls"].isin(["operating", "unclassified_out"])].groupby("category")["amount"].sum().sort_values(ascending=False)
    udhaar_given = collected = 0.0
    n_cleared = 0
    if obligations is not None and len(obligations):
        o = obligations.copy()
        for c in ("issue_date", "paid_date"):
            o[c] = pd.to_datetime(o[c])
        rec = o[o["kind"] == "receivable"]
        udhaar_given = money(rec.loc[(rec["issue_date"] >= start) & (rec["issue_date"] <= a), "amount"].sum())
        paid = rec[(rec["paid_date"] >= start) & (rec["paid_date"] <= a)]
        collected = money(paid["amount"].sum())
        n_cleared = int(len(paid))
    active_days = int(w["date"].nunique())
    return {
        "status": "ok",
        "period": [str(start.date()), str(a.date())],
        "this": this,
        "previous": prev,
        "best_day": best_day,
        "top_customer": top_customer,
        "biggest_expense": biggest,
        "top_costs": [{"category": c, "amount": money(v)} for c, v in cats.head(3).items()],
        "udhaar_given": udhaar_given,
        "collected": collected,
        "invoices_cleared": n_cleared,
        "active_days": active_days,
        "net": money(this["money_in"] - this["money_out"]),
        "record_ids": w["txn_id"].tolist(),
    }


def is_cost(category: str, direction: str) -> bool:
    return classify(category, direction) in ("operating", "unclassified_out")
