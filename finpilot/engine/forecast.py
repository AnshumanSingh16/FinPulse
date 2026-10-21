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
    # Learned from the business's own history (used by the cash autopilot; off by default for the plain forecast):
    customer_delays: bool = False   # expect each customer's invoice on its due date + that customer's usual delay
    recurring: bool = False         # monthly payments to/from the same party (rent, salaries, EMIs, retainers) on their usual day
    billing_cycles: bool = False    # typical flows in an invoiced category start one billing cycle after its last scheduled item


def customer_delay_days(obligations: pd.DataFrame | None) -> tuple[dict[str, int], int]:
    """Median days late per customer (3+ paid invoices), and for everyone together."""
    if obligations is None or not len(obligations):
        return {}, 0
    o = obligations[(obligations["kind"] == "receivable") & (obligations["status"] == "paid")]
    late = (pd.to_datetime(o["paid_date"]) - pd.to_datetime(o["due_date"])).dt.days.clip(lower=0).dropna()
    if not len(late):
        return {}, 0
    per = {k: int(round(g.median())) for k, g in late.groupby(o.loc[late.index, "counterparty"]) if len(g) >= 3}
    return per, int(round(late.median()))


def recurring_payments(ledger: pd.DataFrame, as_of, months: int = 6, obligations: pd.DataFrame | None = None) -> list[dict]:
    """Monthly payments that repeat: same party, category and direction; at least 3 of the last `months` months; amounts within
    15% of each other; about a month apart. Series already covered by an unpaid invoice/bill for that party are left to it."""
    a = ts(as_of)
    df = prepare_ledger(ledger)
    df = df[(df["date"] <= a) & (df["date"] > a - pd.DateOffset(months=months)) & ~df["cls"].isin(RUN_RATE_EXCLUDED)]
    covered: set[tuple] = set()
    if obligations is not None and len(obligations):
        pend = obligations[obligations["status"] == "pending"]
        covered = set(zip(pend["counterparty"].astype(str), pend["category"].astype(str)))
    out = []
    for (party, cat, direction), g in df.groupby(["counterparty", "category", "direction"]):
        if (str(party), str(cat)) in covered or len(g) < 3 or str(party) in ("", "Day-to-day"):
            continue
        g = g.sort_values("date")
        if g["date"].dt.to_period("M").nunique() < len(g) or g["date"].dt.to_period("M").nunique() < 3:
            continue  # more than one a month, or too few months
        amt = g["amount"].tail(3)
        if amt.std(ddof=0) > 0.15 * amt.mean():
            continue
        gaps = g["date"].diff().dt.days.dropna()
        if not (25 <= gaps.median() <= 35):
            continue
        if (a - g["date"].iloc[-1]).days > 40:
            continue  # stopped
        out.append({"counterparty": party, "category": cat, "direction": direction, "amount": money(float(amt.median())),
                    "day": int(round(g["date"].dt.day.tail(3).median())), "last": g["date"].iloc[-1], "txn_ids": g["txn_id"].tolist()})
    return out


def billing_cycle_days(obligations: pd.DataFrame | None) -> dict[str, int]:
    """Per category: the usual number of days between one invoice/bill and the next to the same party (3+ items)."""
    if obligations is None or not len(obligations):
        return {}
    o = obligations.copy()
    o["due_date"] = pd.to_datetime(o["due_date"])
    out = {}
    for cat, g in o.groupby("category"):
        gaps = []
        for _, h in g.groupby("counterparty"):
            if len(h) >= 3:
                gaps.extend(h["due_date"].sort_values().diff().dt.days.dropna().tolist())
        if len(gaps) >= 2:
            out[cat] = int(min(45, max(1, round(float(pd.Series(gaps).median())))))
    return out


def one_off_ids(ledger: pd.DataFrame, as_of, days: int) -> set[str]:
    """Payments that shouldn't be treated as typical: the extra copy of a likely duplicate, rare large
    payments, and outliers at least twice their category's median."""
    from finpilot.engine.expenses import unusual_transactions

    out: set[str] = set()
    for f in unusual_transactions(ledger, as_of, lookback_days=days)["flags"]:
        if f["type"] == "possible_duplicate":
            out.update(f["txn_ids"][1:])
        elif f["type"] == "rare_large_payment" and not _seen_before(ledger, f):
            # A large payment in a young category is only a one-off if nothing like it was paid before
            # (a monthly salary in the 3rd month of records is typical, not rare).
            out.update(f["txn_ids"])
        elif f["type"] == "outlier" and f["amount"] >= 2 * (f["amount"] - f["excess"]):
            out.update(f["txn_ids"])
    return out


def _seen_before(ledger: pd.DataFrame, flag: dict, tolerance: float = 0.25) -> bool:
    d = pd.to_datetime(ledger["date"])
    prior = ledger[(ledger["category"] == flag["category"]) & (d < pd.Timestamp(flag["date"])) & (ledger["direction"] == "out")]["amount"]
    return bool(((prior - flag["amount"]).abs() <= tolerance * flag["amount"]).any())


def invoiced_txn_ids(ledger: pd.DataFrame, obligations: pd.DataFrame | None) -> set[str]:
    """Bank lines that are the payment of a recorded invoice or bill (same party, amount and date as its payment)."""
    if obligations is None or not len(obligations):
        return set()
    o = obligations[obligations["status"] == "paid"][["counterparty", "amount", "paid_date"]].copy()
    o["key"] = o["counterparty"].astype(str) + "|" + o["amount"].round(0).astype(str) + "|" + pd.to_datetime(o["paid_date"]).dt.strftime("%Y-%m-%d")
    led = ledger.copy()
    led["key"] = led["counterparty"].astype(str) + "|" + led["amount"].round(0).astype(str) + "|" + pd.to_datetime(led["date"]).dt.strftime("%Y-%m-%d")
    return set(led.loc[led["key"].isin(set(o["key"])), "txn_id"])


def run_rate_split(ledger: pd.DataFrame, obligations: pd.DataFrame | None, as_of, months: int = 3) -> pd.DataFrame:
    """The run rate per category, split into money that comes through invoices/bills (`billed`) and money that doesn't
    (`unbilled`, e.g. counter sales). Invoices and bills already in the books cover the billed part for their cycle."""
    total = run_rate(ledger, as_of, months)
    billed_ids = invoiced_txn_ids(ledger, obligations)
    pend_pairs: set[tuple] = set()
    if obligations is not None and len(obligations):
        pend = obligations[obligations["status"] == "pending"]
        pend_pairs = set(zip(pend["category"].astype(str), pend["counterparty"].astype(str)))
    pair = pd.MultiIndex.from_arrays([ledger["category"].astype(str), ledger["counterparty"].astype(str)])
    covered_mask = ~ledger["txn_id"].isin(billed_ids) & pair.isin(list(pend_pairs))

    def part(mask) -> pd.Series:
        if not mask.any():
            return pd.Series(dtype=float)
        return run_rate(ledger[mask], as_of, months).set_index("category")["monthly"]

    total["billed"] = total["category"].map(part(ledger["txn_id"].isin(billed_ids))).fillna(0.0)
    # paid to/by a party that already has a scheduled item in the books (e.g. payroll, rent): covered by those items
    total["covered"] = total["category"].map(part(covered_mask)).fillna(0.0)
    total["unbilled"] = (total["monthly"] - total["billed"] - total["covered"]).round(2)
    return total


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
        delays, pooled_delay = customer_delay_days(o) if opt.customer_delays else ({}, 0)
        for r in pend.itertuples():
            if r.kind == "receivable":
                if r.due_date < start:
                    if not opt.include_overdue_receivables:
                        excluded.append({"item_id": r.item_id, "counterparty": r.counterparty, "amount": money(r.amount), "reason": "overdue receivable not counted"})
                        continue
                    when = start + pd.Timedelta(days=opt.overdue_receivable_days)
                else:
                    when = r.due_date + pd.Timedelta(days=opt.receivable_delay_days + (delays.get(r.counterparty, pooled_delay) if opt.customer_delays else 0))
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
        if opt.customer_delays:
            assumptions.append("Each customer's invoices are expected on the due date plus that customer's usual delay "
                               f"(median of their past payments; {pooled_delay} days for customers with fewer than 3 past payments).")
        assumptions.append("Pending payables are paid on their due dates; overdue payables on the first day.")
        if opt.include_overdue_receivables:
            assumptions.append(f"Overdue receivables are collected {opt.overdue_receivable_days} days from today.")
        elif excluded:
            assumptions.append(f"Overdue receivables ({sum(e['amount'] for e in excluded):,.0f}) are NOT counted as incoming.")
    else:
        limitations.append("No invoices or bills were provided: scheduled inflows and outflows are unknown.")

    rr_ledger = ledger
    if opt.recurring and opt.include_run_rate:
        series = recurring_payments(ledger, start, obligations=o if not o.empty else None)
        for r in series:
            # next occurrences on the usual day of the month, from about a month after the last one
            month = (r["last"] + pd.Timedelta(days=20)).to_period("M")
            while True:
                when = month.to_timestamp() + pd.Timedelta(days=min(r["day"], month.days_in_month) - 1)
                if when > end:
                    break
                if when > start:
                    sign = 1 if r["direction"] == "in" else -1
                    flows.append({"date": when, "amount": sign * r["amount"], "label": f"{r['counterparty']} (monthly)", "source": "recurring",
                                  "category": r["category"], "kind": "recurring"})
                month += 1
        if series:
            assumptions.append(f"{len(series)} monthly payment(s) that repeat in your bank lines are expected on their usual day: "
                               + ", ".join(f"{r['counterparty']} {r['amount']:,.0f} around the {r['day']}" for r in series[:6]) + ".")
            rec_ids = {i for r in series for i in r["txn_ids"]}
            rr_ledger = ledger[~ledger["txn_id"].isin(rec_ids)]

    if opt.include_run_rate:
        rr = run_rate_split(rr_ledger, obligations, start, opt.run_rate_months) if opt.billing_cycles else run_rate(rr_ledger, start, opt.run_rate_months)
        win = rr.attrs.get("window")
        sched_last = (
            {}
            if o.empty
            else o[o["status"] == "pending"].groupby("category")["due_date"].max().to_dict()
        )
        total_monthly = 0.0
        cycles = billing_cycle_days(o) if opt.billing_cycles and not o.empty else {}
        for r in rr.itertuples():
            if abs(r.monthly) < 1:
                continue
            if opt.billing_cycles:
                # money that doesn't come through invoices/bills is typical from tomorrow; the invoiced part is covered by the
                # invoices/bills already in the books until one billing cycle after the last of them
                last = sched_last.get(r.category)
                parts = [(r.unbilled, start), (r.covered, max(start, last) if last is not None else start)]
                if abs(r.billed) >= 1:
                    parts.append((r.billed, max(start, last + pd.Timedelta(days=cycles.get(r.category, 0))) if last is not None else start))
            else:
                parts = [(r.monthly, max(start, sched_last.get(r.category, start)))]
            for monthly, begin in parts:
                if abs(monthly) < 1:
                    continue
                day = begin + pd.Timedelta(days=1)
                per_day = monthly * 12 / 365
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
