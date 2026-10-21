"""
Cash in two weeks — a scenario you can change, not a promise.

Starts from today's cash and the same forecast the autopilot uses (recorded bills, expected collections with each
customer's usual delay, regular payments, typical day-to-day sales and costs), then lets the owner change the
assumptions: which collections they believe will arrive, which overdue customers will pay, whether to hold a bill,
how strong sales are, and a planned purchase. Every line is Python arithmetic; the waterfall adds up to the end balance.
"""

from __future__ import annotations

import pandas as pd

from finpilot.data.schema import Evidence
from finpilot.engine.common import fmt_inr, money, ts
from finpilot.engine.forecast import ForecastOptions, forecast_cash_flow

OVERDUE_PAY_IN_DAYS = 7


def outlook(ledger, balances, obligations, as_of, safety: float, days: int = 14, *, skip: tuple[str, ...] = (),
            overdue_pay: tuple[str, ...] = (), sales_pct: float = 100.0, purchase: dict | None = None,
            commitments: list[dict] | None = None, covered: frozenset = frozenset()) -> dict:
    a = ts(as_of)
    days = max(7, min(int(days), 45))
    f = forecast_cash_flow(ledger, balances, obligations, a, ForecastOptions(horizon_days=days, include_run_rate=True, min_buffer=safety,
                                                                    extra_flows=commitments or [], customer_delays=True, billing_cycles=True, recurring=True))
    if f["status"] != "ok":
        return {"status": f["status"], "message": f.get("message", "A dated bank balance is needed to work out cash ahead.")}
    daily = pd.DataFrame(f["daily"])
    daily["date"] = pd.to_datetime(daily["date"])
    sched = pd.DataFrame(f["scheduled_items"] or [], columns=["date", "amount", "label", "source", "category", "kind"])
    sched["date"] = pd.to_datetime(sched["date"])
    end = a + pd.Timedelta(days=days)
    sched = sched[(sched["date"] > a) & (sched["date"] <= end)]

    # typical (unscheduled) money in and out per day = the forecast's day totals minus the scheduled items on that day
    pos = sched[sched["amount"] > 0].groupby("date")["amount"].sum()
    neg = -sched[sched["amount"] < 0].groupby("date")["amount"].sum()
    daily = daily.set_index("date")
    typical_in = (daily["inflow"] - pos.reindex(daily.index).fillna(0)).clip(lower=0)
    typical_out = (daily["outflow"] - neg.reindex(daily.index).fillna(0)).clip(lower=0)
    scale = max(0.0, min(float(sales_pct), 200.0)) / 100

    items = []
    is_obl = set(obligations["item_id"]) if obligations is not None and len(obligations) else set()
    for i, r in enumerate(sched.sort_values("date").itertuples()):
        if r.source in is_obl:
            group = "collection" if r.amount > 0 else "bill"
        elif str(r.source).split(":")[0] in ("collect", "defer", "pause", "discount"):
            group = "approved"
        else:
            group = "regular_in" if r.amount > 0 else "regular_out"
        iid = r.source if r.source in is_obl else f"{r.source}:{r.date.date()}:{i}"
        items.append({"id": iid, "date": str(r.date.date()), "label": r.label, "amount": money(r.amount), "group": group,
                      "included": iid not in skip, "category": r.category, "record": r.source in is_obl})
    overdue = []
    for x in f.get("excluded_items") or []:
        if x.get("reason", "").startswith("overdue receivable") and x["item_id"] not in covered:
            on = x["item_id"] in overdue_pay
            overdue.append({"id": x["item_id"], "party": x["counterparty"], "amount": money(x["amount"]), "included": on,
                            "date": str((a + pd.Timedelta(days=OVERDUE_PAY_IN_DAYS)).date())})
    extra = [{"id": o["id"], "date": o["date"], "label": f"{o['id']} from {o['party']} (overdue)", "amount": o["amount"], "group": "overdue", "included": True}
             for o in overdue if o["included"]]
    if purchase and float(purchase.get("amount") or 0) > 0:
        pd_ = ts(purchase.get("date") or a + pd.Timedelta(days=1))
        pd_ = min(max(pd_, a + pd.Timedelta(days=1)), end)
        extra.append({"id": "purchase", "date": str(pd_.date()), "label": str(purchase.get("label") or "Planned purchase")[:60],
                      "amount": -money(float(purchase["amount"])), "group": "purchase", "included": True})

    # rebuild the running balance from the chosen assumptions
    flows = pd.Series(0.0, index=daily.index)
    for it in items + extra:
        if it["included"]:
            d = pd.Timestamp(it["date"])
            if d in flows.index:
                flows[d] += it["amount"]
    flows += typical_in * scale - typical_out
    flows.iloc[0] = 0.0
    bal = f["starting_cash"] + flows.cumsum()
    lo_date = bal.idxmin()
    below = bal[bal < safety]

    def total(group, sign=1):
        return money(sum(it["amount"] for it in items + extra if it["group"] == group and it["included"]) * sign)

    t_in, t_out = money(typical_in.iloc[1:].sum() * scale), money(typical_out.iloc[1:].sum())
    water = [
        {"key": "start", "label": "Cash today", "amount": money(f["starting_cash"])},
        {"key": "collection", "label": "Customer payments expected", "amount": total("collection")},
        {"key": "overdue", "label": "Overdue customers you expect to pay", "amount": total("overdue")},
        {"key": "regular_in", "label": "Other regular money in", "amount": total("regular_in")},
        {"key": "approved", "label": "Moves you approved", "amount": total("approved")},
        {"key": "typical_in", "label": f"Day-to-day sales ({round(scale * 100)}% of usual)", "amount": t_in},
        {"key": "bill", "label": "Bills and salaries due", "amount": total("bill")},
        {"key": "regular_out", "label": "Regular payments (rent, subscriptions, drawings…)", "amount": total("regular_out")},
        {"key": "typical_out", "label": "Day-to-day costs", "amount": -t_out},
        {"key": "purchase", "label": "Your planned purchase", "amount": total("purchase")},
    ]
    water = [w for w in water if w["key"] == "start" or abs(w["amount"]) >= 1]
    end_bal = money(bal.iloc[-1])
    used = [it["id"] for it in items + extra if it["included"] and (it.get("record") or it["group"] == "overdue")]
    skipped = [it for it in items if not it["included"]]
    unverified = ["Whether each customer actually pays on the expected date — FinPilot uses each customer's own past delays, but they decide.",
                  "Day-to-day sales and costs are your recent average; a festival, a lost client or a one-off can change them."]
    if overdue and not any(o["included"] for o in overdue):
        unverified.append(f"Overdue invoices ({fmt_inr(sum(o['amount'] for o in overdue))}) are left out — tick them if you're confident they'll pay.")
    return {
        "status": "ok", "as_of": str(a.date()), "days": days, "end_date": str(end.date()), "safety": money(safety),
        "start": money(f["starting_cash"]), "end": end_bal, "change": money(end_bal - f["starting_cash"]),
        "lowest": money(bal.min()), "lowest_date": str(lo_date.date()), "below_cushion_from": str(below.index[0].date()) if len(below) else None,
        "runs_out": str(bal[bal < 0].index[0].date()) if (bal < 0).any() else None,
        "daily": [{"date": str(d.date()), "balance": money(v)} for d, v in bal.items()],
        "waterfall": water, "items": items, "overdue": overdue, "purchase": next((e for e in extra if e["group"] == "purchase"), None),
        "assumptions_used": {"sales_pct": round(scale * 100), "skipped": [s["id"] for s in skipped], "overdue_pay": [o["id"] for o in overdue if o["included"]]},
        "evidence": Evidence(
            method=("Cash in two weeks = cash today + each included collection, bill and regular payment on its expected date "
                    "+ day-to-day sales (your recent average, scaled by your setting) − day-to-day costs − your planned purchase. "
                    "The rows of the breakdown add up to the end balance."),
            assumptions=(f"Customer payments arrive on the due date plus that customer's usual delay; overdue invoices you tick arrive within {OVERDUE_PAY_IN_DAYS} days.",
                         "Bills and salaries are paid on their due dates unless you untick them.",
                         "Day-to-day sales and costs follow the average of the last three months, spread evenly."),
            limitations=("A scenario on your records and the assumptions you chose — not a prediction.",),
            record_ids=tuple(used), period=(str(a.date()), str(end.date())), unverified=tuple(unverified),
        ).to_dict() | {"formula": " + ".join(f"{w['label']} {fmt_inr(w['amount'])}" for w in water) + f" = {fmt_inr(end_bal)}"},
    }
