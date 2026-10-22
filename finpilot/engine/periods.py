"""
Cash by month or quarter: what actually happened (from the ledger) followed by the forecast, on one timeline.

Actual balances are walked back from today's cash position with the ledger's own movements (the same records the
cash position is built from), so the past and the forecast join at today without a gap. Forecast periods come from
the same daily forecast as the 13-week view. Periods cut by today are split into their actual and forecast parts.
"""

from __future__ import annotations

import pandas as pd

from finpilot.engine.common import money, prepare_ledger, ts


def _bucket(dates: pd.Series, by: str) -> pd.Series:
    return dates.dt.to_period("Q" if by == "quarter" else "M")


def _label(p: pd.Period, by: str) -> str:
    return f"Q{p.quarter} {p.year}" if by == "quarter" else p.strftime("%b %Y")


def periods(f: dict, ledger: pd.DataFrame, as_of, by: str = "month", history: int | None = None) -> dict:
    a = ts(as_of)
    by = "quarter" if by == "quarter" else "month"
    history = history if history is not None else (4 if by == "quarter" else 12)
    start_cash = float(f["starting_cash"])

    # ---- actual: daily balance walked back from today's cash with the ledger's movements
    led = prepare_ledger(ledger)
    led = led[led["date"] <= a]
    flows = led.groupby("date")["signed"].sum().sort_index()
    first = (a.to_period("Q" if by == "quarter" else "M") - history).start_time
    first = max(first, led["date"].min()) if len(led) else a
    days = pd.date_range(first, a, freq="D")
    net = flows.reindex(days).fillna(0.0)
    after = net[::-1].cumsum()[::-1].shift(-1).fillna(0.0)  # movements after each day, up to today
    actual = pd.DataFrame({"date": days, "balance": start_cash - after.values})
    ins = led[led["direction"] == "in"].groupby("date")["amount"].sum().reindex(days).fillna(0.0)
    outs = led[led["direction"] == "out"].groupby("date")["amount"].sum().reindex(days).fillna(0.0)
    actual["inflow"], actual["outflow"], actual["kind"] = ins.values, outs.values, "actual"

    # ---- forecast: the daily forecast after today
    fc = pd.DataFrame(f["daily"])
    fc["date"] = pd.to_datetime(fc["date"])
    fc = fc[fc["date"] > a].assign(kind="forecast")
    items = pd.DataFrame(f["scheduled_items"] or [], columns=["date", "amount", "label", "source", "category", "kind"])
    items["date"] = pd.to_datetime(items["date"])

    daily = pd.concat([actual[["date", "balance", "inflow", "outflow", "kind"]], fc[["date", "balance", "inflow", "outflow", "kind"]]], ignore_index=True)
    daily["p"] = _bucket(daily["date"], by)
    out = []
    for p, g in daily.groupby("p", sort=True):
        prev = daily[daily["date"] < g["date"].iloc[0]]
        opening = float(prev["balance"].iloc[-1]) if len(prev) else float(g["balance"].iloc[0] - g["inflow"].iloc[0] + g["outflow"].iloc[0])
        kinds = set(g["kind"])
        lo = g.loc[g["balance"].idxmin()]
        its = items[(items["date"] > a) & (_bucket(items["date"], by) == p)] if len(items) else items
        top = its.reindex(its["amount"].abs().sort_values(ascending=False).index).head(8) if len(its) else its
        out.append({
            "period": str(p), "label": _label(p, by), "start": str(p.start_time.date()), "end": str(p.end_time.date()),
            "kind": "actual" if kinds == {"actual"} else "forecast" if kinds == {"forecast"} else "mixed",
            "partial": bool(g["date"].iloc[0] > p.start_time or g["date"].iloc[-1] < p.end_time.normalize()),
            "covers": [str(g["date"].iloc[0].date()), str(g["date"].iloc[-1].date())],
            "money_in": money(g["inflow"].sum()), "money_out": money(g["outflow"].sum()),
            "actual_in": money(g.loc[g["kind"] == "actual", "inflow"].sum()), "actual_out": money(g.loc[g["kind"] == "actual", "outflow"].sum()),
            "opening": money(opening), "closing": money(g["balance"].iloc[-1]),
            "lowest": money(lo["balance"]), "lowest_date": str(lo["date"].date()),
            "items": [{"date": str(r.date.date()), "label": r.label, "amount": money(r.amount), "source": r.source, "kind": r.kind} for r in top.itertuples()],
        })
    return {
        "status": "ok", "by": by, "as_of": str(a.date()), "today": money(start_cash),
        "daily": [{"date": str(r.date.date()), "balance": money(r.balance), "kind": r.kind} for r in daily.itertuples()],
        "periods": out,
        "method": ("Past balances: today's cash position minus the ledger movements after each day. Money in and out: ledger totals per period "
                   "(transfers and loans included, as they move cash). Forecast: the same daily forecast as the plan, with the moves you approved."),
    }
