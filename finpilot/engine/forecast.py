"""
Cash-flow forecast for 30, 60 and 90 days (or any horizon).

    start      the cash position on the as-of date (needs a dated balance — see cash.py)
    + inflows  pending receivables on their due dates (optionally delayed / partly collected);
               overdue receivables only if you choose to count them, on a date you choose
    − outflows pending payables on their due dates; overdue payables on day 1
    ± optional typical unscheduled flows: the average of the last N full months of ledger categories
               that have no scheduled items (or after a category's last scheduled item), spread evenly
    ± extra flows passed in (e.g. a purchase being simulated)

Every included item is listed, every assumption is written out, and nothing here is a prediction:
it is arithmetic on what is known plus the assumptions shown.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from finpilot.data.schema import Evidence
from finpilot.engine.cash import cash_position
from finpilot.engine.common import last_full_month, money, prepare_ledger, ts

RUN_RATE_EXCLUDED = ("capex", "financing_in", "transfer", "other_in", "unclassified_in")


@dataclass
class ForecastOptions:
    horizon_days: int = 90
    receivable_delay_days: int = 0
    receivable_collection_pct: float = 100.0
    include_overdue_receivables: bool = False
    overdue_receivable_days: int = 30
    include_run_rate: bool = False
    run_rate_months: int = 3
    min_buffer: float | None = None
    extra_flows: list[dict] = field(default_factory=list)  # {"date", "amount" (signed), "label"}


def one_off_ids(ledger: pd.DataFrame, as_of, days: int) -> set[str]:
    """Payments that shouldn't be treated as typical: the extra copy of a likely duplicate, rare large
    payments, and outliers at least twice their category's median."""
    from finpilot.engine.expenses import unusual_transactions

    out: set[str] = set()
    for f in unusual_transactions(ledger, as_of, lookback_days=days)["flags"]:
        if f["type"] == "possible_duplicate":
            out.update(f["txn_ids"][1:])
        elif f["type"] == "rare_large_payment":
            out.update(f["txn_ids"])
        elif f["type"] == "outlier" and f["amount"] >= 2 * (f["amount"] - f["excess"]):
            out.update(f["txn_ids"])
    return out


def run_rate(ledger: pd.DataFrame, as_of, months: int = 3) -> pd.DataFrame:
    """Average monthly net flow per category over the last `months` full months, without one-offs."""
    df = prepare_ledger(ledger)
    _, end = last_full_month(as_of)
    start = (end - pd.DateOffset(months=months - 1)).replace(day=1)
    skip = one_off_ids(ledger, end, (end - start).days + 1)
    win = df[
        (df["date"] >= start)
        & (df["date"] <= end)
        & ~df["cls"].isin(RUN_RATE_EXCLUDED)
        & ~df["txn_id"].isin(skip)
    ]
    covered_months = win["date"].dt.to_period("M").nunique()
    g = win.groupby(["category", "cls"])["signed"].sum().reset_index()
    g["monthly"] = (g["signed"] / months).round(2)
    g.attrs["window"] = (str(start.date()), str(end.date()))
    g.attrs["months_with_data"] = int(covered_months)
    g.attrs["excluded_one_offs"] = sorted(skip)
    return g[["category", "cls", "monthly"]]


def forecast_cash_flow(
    ledger: pd.DataFrame,
    balances: pd.DataFrame | None,
    obligations: pd.DataFrame | None,
    as_of,
    options: ForecastOptions | None = None,
) -> dict:
    opt = options or ForecastOptions()
    start = ts(as_of)
    pos = cash_position(ledger, balances, start)
    if pos["status"] != "ok":
        return {
            "status": "insufficient_data",
            "message": "A forecast needs today's cash position. " + pos["message"],
            "missing": pos.get("missing", []),
            "evidence": pos["evidence"],
        }
    end = start + pd.Timedelta(days=opt.horizon_days)
    flows: list[dict] = []
    assumptions: list[str] = [
        f"Starts from the cash position on {start.date()} ({pos['cash_balance']:,.0f}), "
        f"derived from the balance dated {pos['anchor_balance']['as_of']}.",
    ]
    limitations: list[str] = [
        "This is arithmetic on known items and the assumptions listed — not a prediction. "
        "Its accuracy has not been measured.",
    ]
    excluded: list[dict] = []
    record_ids: list[str] = []

    o = pd.DataFrame() if obligations is None else obligations.copy()
    if not o.empty:
        for c in ("issue_date", "due_date", "paid_date"):
            if c in o:
                o[c] = pd.to_datetime(o[c]).dt.normalize()
        pend = o[o["status"] == "pending"]
        frac = opt.receivable_collection_pct / 100
        for r in pend.itertuples():
            if r.kind == "receivable":
                if r.due_date < start:
                    if not opt.include_overdue_receivables:
                        excluded.append({"item_id": r.item_id, "counterparty": r.counterparty, "amount": money(r.amount), "reason": "overdue receivable not counted"})
                        continue
                    when = start + pd.Timedelta(days=opt.overdue_receivable_days)
                else:
                    when = r.due_date + pd.Timedelta(days=opt.receivable_delay_days)
                amount = r.amount * frac
                label = f"{r.item_id} from {r.counterparty}"
            else:
                when = max(r.due_date, start + pd.Timedelta(days=1))
                amount = -r.amount
                label = f"{r.item_id} to {r.counterparty}"
            if when <= end:
                flows.append({"date": when, "amount": money(amount), "label": label, "source": r.item_id, "category": r.category, "kind": "scheduled"})
                record_ids.append(r.item_id)
        assumptions.append("Pending receivables are received on their due dates" + (f" + {opt.receivable_delay_days} days" if opt.receivable_delay_days else "") + (f", {opt.receivable_collection_pct:g}% collected" if frac != 1 else "") + ".")
        assumptions.append("Pending payables are paid on their due dates; overdue payables on the first day.")
        if opt.include_overdue_receivables:
            assumptions.append(f"Overdue receivables are collected {opt.overdue_receivable_days} days from today.")
        elif excluded:
            assumptions.append(f"Overdue receivables ({sum(e['amount'] for e in excluded):,.0f}) are NOT counted as incoming.")
    else:
        limitations.append("No invoices or bills were provided: scheduled inflows and outflows are unknown.")

    if opt.include_run_rate:
        rr = run_rate(ledger, start, opt.run_rate_months)
        win = rr.attrs.get("window")
        sched_last = (
            {}
            if o.empty
            else o[o["status"] == "pending"].groupby("category")["due_date"].max().to_dict()
        )
        total_monthly = 0.0
        for r in rr.itertuples():
            if abs(r.monthly) < 1:
                continue
            begin = max(start, sched_last.get(r.category, start))
            day = begin + pd.Timedelta(days=1)
            per_day = r.monthly * 12 / 365
            while day <= end:
                flows.append({"date": day, "amount": per_day, "label": f"Typical {r.category.lower()}", "source": "run_rate", "category": r.category, "kind": "assumed"})
                day += pd.Timedelta(days=1)
            total_monthly += r.monthly
        assumptions.append(
            f"Typical unscheduled flows: the average of {win[0]} to {win[1]} per category, spread evenly "
            f"per day (net {total_monthly:,.0f} a month), starting after any scheduled items in that category "
            "so nothing is counted twice. Loans, asset purchases, transfers and one-off inflows are excluded."
            + (
                f" One-off payments left out of the average: {', '.join(rr.attrs['excluded_one_offs'])}."
                if rr.attrs.get("excluded_one_offs")
                else ""
            )
        )
    else:
        limitations.append(
            "Only scheduled items are included. Regular costs and sales without an uploaded bill or invoice "
            "(e.g. raw materials, utilities, retail takings) are missing, so the forecast can look better or "
            "worse than reality. Turn on 'typical unscheduled flows' to add them as an assumption."
        )

    shifted = 0
    for f in opt.extra_flows:
        when = ts(f["date"])
        if when <= start:  # day 0 is today's closing balance, so anything due "today" lands tomorrow
            when, shifted = start + pd.Timedelta(days=1), shifted + 1
        flows.append({"date": when, "amount": money(f["amount"]), "label": f["label"], "source": f.get("source", "scenario"), "category": f.get("category", "Scenario"), "kind": "scenario"})

    if shifted:
        assumptions.append(f"{shifted} scenario item(s) dated on or before {start.date()} are counted on the next day, after today's closing balance.")

    days = pd.date_range(start, end, freq="D")
    fdf = pd.DataFrame(flows) if flows else pd.DataFrame(columns=["date", "amount", "label", "source", "category", "kind"])
    daily_in = fdf[fdf["amount"] > 0].groupby("date")["amount"].sum() if len(fdf) else pd.Series(dtype=float)
    daily_out = -fdf[fdf["amount"] < 0].groupby("date")["amount"].sum() if len(fdf) else pd.Series(dtype=float)
    series = pd.DataFrame(index=days)
    series["inflow"] = daily_in.reindex(days, fill_value=0.0)
    series["outflow"] = daily_out.reindex(days, fill_value=0.0)
    series.loc[start, ["inflow", "outflow"]] = 0.0  # day 0 is today's closing position
    series["balance"] = pos["cash_balance"] + (series["inflow"] - series["outflow"]).cumsum()
    series = series.round(2)

    checkpoints = []
    for d in (30, 60, 90, opt.horizon_days):
        if d > opt.horizon_days or any(c["days"] == d for c in checkpoints):
            continue
        day = start + pd.Timedelta(days=d)
        part = series.loc[:day]
        checkpoints.append(
            {
                "days": d,
                "date": str(day.date()),
                "balance": money(series.loc[day, "balance"]),
                "inflows": money(part["inflow"].sum()),
                "outflows": money(part["outflow"].sum()),
            }
        )
    low_day = series["balance"].idxmin()
    below = None
    if opt.min_buffer is not None:
        under = series[series["balance"] < opt.min_buffer]
        below = str(under.index[0].date()) if len(under) else None
        assumptions.append(f"Minimum cash buffer: {opt.min_buffer:,.0f}.")
    negative = series[series["balance"] < 0]

    items = (
        fdf[fdf["kind"] != "assumed"].sort_values("date").assign(date=lambda d: d["date"].dt.date.astype(str)).to_dict(orient="records")
        if len(fdf)
        else []
    )
    assumed_total = money(fdf.loc[fdf["kind"] == "assumed", "amount"].sum()) if len(fdf) else 0.0
    return {
        "status": "ok",
        "as_of": str(start.date()),
        "horizon_days": opt.horizon_days,
        "starting_cash": pos["cash_balance"],
        "checkpoints": checkpoints,
        "lowest_balance": money(series.loc[low_day, "balance"]),
        "lowest_balance_date": str(low_day.date()),
        "first_date_below_buffer": below,
        "first_negative_date": str(negative.index[0].date()) if len(negative) else None,
        "scheduled_items": items,
        "assumed_flows_total": assumed_total,
        "excluded_items": excluded,
        "daily": series.reset_index(names="date").assign(date=lambda d: d["date"].dt.date.astype(str)).to_dict(orient="records"),
        "evidence": Evidence(
            method=(
                "Daily running balance: starting cash + each day's included inflows − outflows. "
                "Checkpoint balances are read from that series."
            ),
            assumptions=tuple(assumptions),
            limitations=tuple(limitations + pos["evidence"]["limitations"]),
            record_ids=tuple(record_ids),
            period=(str(start.date()), str(end.date())),
        ).to_dict(),
    }
