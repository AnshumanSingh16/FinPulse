"""
Fast-forward (demo books only): live the next few days the way they could plausibly happen, so the agents can be
watched working over time — noticing a missed checkpoint, switching to Plan B, drawing on a standby overdraft, learning.

Each day, in order:
  1. bills, salaries and other payables due that day (or already overdue) are paid
  2. customers pay on the day chosen for them at the start (from their own payment history, or the scenario)
  3. typical day-to-day sales and costs happen per category, at the forecast's own daily rate (with a little variation),
     except spending the owner approved pausing
  4. if the owner approved a standby overdraft and the balance would end the day below the safety level, it is drawn

Scenarios for customers already more than 30 days late:
  usual     they pay after a reminder with the learned chance, otherwise rarely
  defaults  they do not pay at all
  pays      they pay about 5 days after a reminder

Everything written is marked "Simulated" so it can never be mistaken for a real record.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from finpilot.data import khata
from finpilot.engine import risk
from finpilot.engine.cash import cash_position
from finpilot.engine.common import money, ts
from finpilot.engine.forecast import run_rate

SCENARIOS = ("usual", "defaults", "pays")
REF = "Simulated"


@dataclass
class Plan:
    reminded: dict[str, pd.Timestamp] = field(default_factory=dict)   # customer -> day the reminder went
    paused: dict[str, pd.Timestamp] = field(default_factory=dict)     # category -> paused until
    overdraft_limit: float = 0.0
    overdraft_drawn: float = 0.0
    safety: float = 0.0
    learned: dict[str, float] = field(default_factory=dict)


def _ledger_row(t: khata.Tables, day, amount, direction, category, party, description) -> str:
    tid = khata._next_id(t.ledger["txn_id"], "S", 5)
    row = {"txn_id": tid, "date": ts(day), "description": description, "counterparty": party, "category": category,
           "direction": direction, "amount": money(amount), "payment_mode": "NEFT", "reference": REF}
    t.ledger = pd.concat([t.ledger, pd.DataFrame([row])], ignore_index=True)
    t.ledger["date"] = pd.to_datetime(t.ledger["date"])
    return tid


def arrivals(t: khata.Tables, as_of, days: int, scenario: str, p: Plan, rng: np.random.Generator) -> dict[str, pd.Timestamp | None]:
    """When each unpaid customer invoice will be paid in this run (None = not within the window)."""
    a = ts(as_of)
    o = t.obligations
    if o is None or not len(o):
        return {}
    o = o.copy()
    for c in ("due_date", "paid_date"):
        o[c] = pd.to_datetime(o[c])
    recv = o[o["kind"] == "receivable"]
    paid = recv[(recv["status"] == "paid") & recv["paid_date"].notna()]
    hist_all = (paid["paid_date"] - paid["due_date"]).dt.days.clip(lower=0)
    pooled = hist_all.to_numpy() if len(hist_all) else np.array([0])
    by_party = {k: g.to_numpy() for k, g in hist_all.groupby(paid["counterparty"]) if len(g) >= 3}
    pend = recv[recv["status"] == "pending"]
    late = pend[pend["due_date"] < a].groupby("counterparty")["due_date"].min()
    stuck = {c for c, d in late.items() if (a - d).days > 30}
    out: dict[str, pd.Timestamp | None] = {}
    end = a + pd.Timedelta(days=days)
    for r in pend.itertuples():
        when: pd.Timestamp | None
        if r.counterparty in stuck:
            sent = p.reminded.get(r.counterparty)
            if scenario == "defaults":
                when = None
            elif scenario == "pays":
                when = (sent + pd.Timedelta(days=5)) if sent is not None else None
            elif sent is not None:
                chance = p.learned.get(r.counterparty, risk.REMINDED_PAY_PROB)
                when = sent + pd.Timedelta(days=int(rng.integers(4, 15))) if rng.random() < chance else None
            else:
                when = a + pd.Timedelta(days=int(rng.integers(1, 91))) if rng.random() < risk.STUCK_PAY_PROB else None
            if when is not None:
                when = max(when, r.due_date)
        elif r.due_date < a:
            sent = p.reminded.get(r.counterparty)
            if sent is not None:
                when = sent + pd.Timedelta(days=int(rng.integers(3, 11))) if rng.random() < risk.REMINDED_LATE_PAY_PROB else None
            else:
                when = a + pd.Timedelta(days=int(rng.integers(1, 31))) if rng.random() < risk.LATE_PAY_PROB else None
        else:
            hist = by_party.get(r.counterparty, pooled)
            when = r.due_date + pd.Timedelta(days=int(rng.choice(hist)))
        out[r.item_id] = max(when, a + pd.Timedelta(days=1)) if when is not None and when <= end else None
    return out


def advance(t: khata.Tables, as_of, days: int, scenario: str, p: Plan, seed: int = 11, on_day=None) -> tuple[khata.Tables, list[dict]]:
    """Live `days` days. Returns the new tables and one entry per day: {"date", "items": [...], "net", "balance"}.
    `on_day(day, tables)` is called after each day (the agents' monitor)."""
    if scenario not in SCENARIOS:
        raise ValueError(f"scenario must be one of {', '.join(SCENARIOS)}")
    rng = np.random.default_rng(seed)
    a = ts(as_of)
    t = t.copy()
    pos = cash_position(t.ledger, t.balances, a)
    balance = float(pos["cash_balance"]) if pos["status"] == "ok" else 0.0
    when = arrivals(t, a, days, scenario, p, rng)
    rr = run_rate(t.ledger, a)
    o = t.obligations.copy() if t.obligations is not None else None
    if o is not None:
        for c in ("issue_date", "due_date", "paid_date"):
            o[c] = pd.to_datetime(o[c])
        t.obligations = o
    sched_last = {} if o is None else o[o["status"] == "pending"].groupby("category")["due_date"].max().to_dict()
    noise = {r.category: float(np.clip(rng.normal(1, 0.08), 0.8, 1.2)) for r in rr.itertuples()}
    log = []
    for k in range(1, days + 1):
        d = a + pd.Timedelta(days=k)
        items, net = [], 0.0
        o = t.obligations
        if o is not None:
            due = o[(o["status"] == "pending") & (o["kind"] == "payable") & (o["due_date"] <= d)]
            for r in due.itertuples():
                _ledger_row(t, d, r.amount, "out", r.category, r.counterparty, f"{r.item_id} {r.description}")
                o.loc[o["item_id"] == r.item_id, ["status", "paid_date"]] = ["paid", d]
                items.append({"kind": "bill", "party": r.counterparty, "amount": -money(r.amount), "id": r.item_id})
                net -= r.amount
            for iid, w in when.items():
                if w is not None and w == d:
                    r = o[o["item_id"] == iid].iloc[0]
                    _ledger_row(t, d, r["amount"], "in", r["category"], r["counterparty"], f"Payment for {iid}")
                    o.loc[o["item_id"] == iid, ["status", "paid_date"]] = ["paid", d]
                    items.append({"kind": "paid_in", "party": r["counterparty"], "amount": money(r["amount"]), "id": iid})
                    net += r["amount"]
        typ_in = typ_out = 0.0
        for r in rr.itertuples():
            if abs(r.monthly) < 1 or d <= sched_last.get(r.category, a):
                continue
            if r.monthly < 0 and r.category in p.paused and d <= p.paused[r.category]:
                continue
            amt = abs(r.monthly) * 12 / 365 * noise[r.category]
            _ledger_row(t, d, amt, "in" if r.monthly > 0 else "out", r.category, "Day-to-day", f"Typical {r.category.lower()}")
            if r.monthly > 0:
                typ_in += amt
            else:
                typ_out += amt
        net += typ_in - typ_out
        items.append({"kind": "typical", "in": money(typ_in), "out": money(typ_out)})
        balance += net
        if p.overdraft_limit > p.overdraft_drawn and balance < p.safety:
            draw = min(p.overdraft_limit - p.overdraft_drawn, float(np.ceil((p.safety - balance) / 10_000) * 10_000))
            _ledger_row(t, d, draw, "in", "Loan Received", "Bank (overdraft)", "Standby overdraft drawn")
            p.overdraft_drawn += draw
            balance += draw
            items.append({"kind": "overdraft", "amount": money(draw), "drawn": money(p.overdraft_drawn), "limit": money(p.overdraft_limit)})
        log.append({"date": str(d.date()), "items": items, "balance": money(balance)})
        if on_day:
            on_day(d, t)
    return t, log
