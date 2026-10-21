"""
Stress test: the same 90-day forecast, run as 1,000 possible futures instead of one.

What varies between futures (everything else is exactly the forecast):
  - when each customer pays: sampled from that customer's own history of days late (paid date − due date);
    customers with little history use everyone's history
  - overdue money: a customer up to 30 days late pays within the horizon with LATE_PAY_PROB;
    one more than 30 days late ("stuck") with STUCK_PAY_PROB, or REMINDED_PAY_PROB after a reminder
  - typical day-to-day sales and costs: scaled each month by a factor drawn from how much they have
    actually varied month to month (capped at ±VARIATION_CAP of one standard deviation)

Bills, salaries, rent and taxes are paid on their due dates in every future. The result is a share of futures,
not a promise: it is only as good as the payment history and the stated assumptions.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from finpilot.engine.common import last_full_month, money, prepare_ledger, ts

N_SIMS = 1000
LATE_PAY_PROB = 0.85
STUCK_PAY_PROB = 0.25
REMINDED_PAY_PROB = 0.6
REMINDED_LATE_PAY_PROB = 0.95
VARIATION_CAP = 0.35
COLLECT_IN_DAYS = 7
DISCOUNT_ACCEPT_PROB = 0.7
PRIOR_STRENGTH = 4  # how many reminders' worth of evidence the starting assumption counts for
SEED = 7


@dataclass
class Model:
    as_of: pd.Timestamp
    horizon: int
    base: np.ndarray            # daily balance (index 0 = today) with every pending customer payment taken out
    typical_in: np.ndarray      # typical (unscheduled) money in per day
    typical_out: np.ndarray
    receivables: list[dict]     # {"party", "amount", "due": day index (may be ≤ 0 if overdue), "kind": due | late | stuck, "id"}
    delays: dict[str, np.ndarray]
    pooled: np.ndarray
    cv_in: float
    cv_out: float
    history_points: int
    reminder_p: dict[str, float]  # learned: chance a stuck customer pays after a reminder, per customer


def learned_reminder_p(outcomes: dict[str, tuple[int, int]] | None) -> dict[str, float]:
    """Beta-style update of the starting assumption with what each customer actually did after reminders: (reminders, paid)."""
    out = {}
    for party, (sent, paid) in (outcomes or {}).items():
        if sent:
            out[party] = (REMINDED_PAY_PROB * PRIOR_STRENGTH + paid) / (PRIOR_STRENGTH + sent)
    return out


def _idx(date, as_of: pd.Timestamp) -> int:
    return int((ts(date) - as_of).days)


def _monthly_cv(ledger: pd.DataFrame, as_of, sign: int, months: int = 6) -> float:
    df = prepare_ledger(ledger)
    _, end = last_full_month(as_of)
    start = (end - pd.DateOffset(months=months - 1)).replace(day=1)
    win = df[(df["date"] >= start) & (df["date"] <= end) & ~df["cls"].isin(("capex", "financing_in", "financing_out", "transfer", "other_in", "unclassified_in"))]
    win = win[win["signed"] * sign > 0]
    s = win.groupby(win["date"].dt.to_period("M"))["signed"].sum().abs()
    if len(s) < 3 or s.mean() <= 0:
        return 0.1
    return float(min(max(s.std(ddof=1) / s.mean(), 0.03), VARIATION_CAP))


def build(ledger: pd.DataFrame, obligations: pd.DataFrame | None, as_of, forecast: dict, stuck_parties: set[str],
          outcomes: dict[str, tuple[int, int]] | None = None) -> Model:
    """`forecast` is the deterministic forecast (late customers' upcoming invoices already set aside, overdue not counted)."""
    a = ts(as_of)
    daily = forecast["daily"]
    horizon = len(daily) - 1
    bal = np.array([d["balance"] for d in daily], dtype=float)
    inflow = np.array([d["inflow"] for d in daily], dtype=float)
    outflow = np.array([d["outflow"] for d in daily], dtype=float)
    sched_in, sched_out = np.zeros(horizon + 1), np.zeros(horizon + 1)
    o = pd.DataFrame() if obligations is None else obligations.copy()
    pending_recv: set[str] = set()
    if len(o):
        for c in ("due_date", "paid_date"):
            o[c] = pd.to_datetime(o[c])
        pending_recv = set(o.loc[(o["kind"] == "receivable") & (o["status"] != "paid"), "item_id"])

    removed = np.zeros(horizon + 1)
    counted: set[str] = set()
    sched_at: dict[str, int] = {}
    for it in forecast["scheduled_items"]:
        i = _idx(it["date"], a)
        if not 0 < i <= horizon:
            continue
        if it["amount"] > 0:
            sched_in[i] += it["amount"]
        else:
            sched_out[i] += -it["amount"]
        if it["source"] in pending_recv and it["amount"] > 0:
            removed[i] += it["amount"]
            counted.add(it["source"])
            sched_at[it["source"]] = i
    base = bal - np.cumsum(removed)

    receivables: list[dict] = []
    delays: dict[str, np.ndarray] = {}
    pooled = np.array([0.0])
    points = 0
    if len(o):
        recv = o[o["kind"] == "receivable"]
        paid = recv[(recv["status"] == "paid") & recv["paid_date"].notna() & recv["due_date"].notna()]
        late_days = (paid["paid_date"] - paid["due_date"]).dt.days.clip(lower=0)
        points = int(len(late_days))
        if points:
            pooled = late_days.to_numpy(dtype=float)
            for p, g in late_days.groupby(paid["counterparty"]):
                if len(g) >= 3:
                    delays[p] = g.to_numpy(dtype=float)
        for r in recv[recv["status"] != "paid"].itertuples():
            i = _idx(r.due_date, a)
            if r.counterparty in stuck_parties:
                kind = "stuck"
            elif i <= 0:
                kind = "late"
            else:
                kind = "due"
            if kind == "due" and r.item_id not in counted:
                continue  # beyond the horizon
            receivables.append({"id": r.item_id, "party": r.counterparty, "amount": float(r.amount), "due": i, "kind": kind, "expected": sched_at.get(r.item_id, i)})
    return Model(a, horizon, base, np.maximum(inflow - sched_in, 0), np.maximum(outflow - sched_out, 0), receivables, delays, pooled,
                 _monthly_cv(ledger, a, 1), _monthly_cv(ledger, a, -1), points, learned_reminder_p(outcomes))


def _paths(m: Model, n: int, extra: np.ndarray | None, reminded: frozenset[str], rng: np.random.Generator, deterministic: bool,
           fails: frozenset[str] = frozenset(), pulled: dict | None = None) -> np.ndarray:
    H = m.horizon
    adds = np.zeros((n, H + 2))
    pulled = pulled or {}
    for r in m.receivables:
        if deterministic:  # exactly the forecast: on the day it expects the money
            if r["kind"] == "due":
                adds[:, r["expected"]] += r["amount"]
            continue
        rows = np.arange(n)
        if r["party"] in fails:  # Plan B: this customer does not pay within the horizon
            continue
        if r["kind"] == "due":
            hist = m.delays.get(r["party"], m.pooled)
            day = r["due"] + rng.choice(hist, size=n).astype(int)
            pays = np.ones(n, dtype=bool)
            if r["id"] in pulled:  # offered an early-payment discount: accepted in some futures, paid early and a little less
                on_day, keep = pulled[r["id"]]
                took = rng.random(n) < DISCOUNT_ACCEPT_PROB
                early = np.clip(on_day + rng.integers(0, 4, n), 1, H + 1)
                np.add.at(adds, (rows[took], early[took]), r["amount"] * keep)
                pays = ~took
        elif r["kind"] == "late":
            if r["party"] in reminded:
                pays, day = rng.random(n) < REMINDED_LATE_PAY_PROB, COLLECT_IN_DAYS + rng.integers(0, 8, n)
            else:
                pays, day = rng.random(n) < LATE_PAY_PROB, rng.integers(1, 31, n)
        else:  # stuck
            if r["party"] in reminded:
                pays, day = rng.random(n) < m.reminder_p.get(r["party"], REMINDED_PAY_PROB), COLLECT_IN_DAYS + rng.integers(0, 15, n)
            else:
                pays, day = rng.random(n) < STUCK_PAY_PROB, rng.integers(1, H + 1, n)
            day = np.maximum(day, r["due"])
        day = np.clip(day, 1, H + 1)  # H + 1 = after the horizon
        np.add.at(adds, (rows[pays], day[pays]), r["amount"])
    paths = m.base[None, :] + np.cumsum(adds[:, : H + 1], axis=1)
    if not deterministic:
        seg = np.minimum(np.arange(H + 1) // 30, 2)
        f_in = np.clip(rng.normal(1, m.cv_in, (n, 3)), 1 - 2 * m.cv_in, 1 + 2 * m.cv_in)[:, seg]
        f_out = np.clip(rng.normal(1, m.cv_out, (n, 3)), 1 - 2 * m.cv_out, 1 + 2 * m.cv_out)[:, seg]
        paths += np.cumsum(m.typical_in[None, :] * (f_in - 1) - m.typical_out[None, :] * (f_out - 1), axis=1)
    if extra is not None:
        paths += extra[None, :]
    return paths


def simulate(m: Model, safety: float, extra: np.ndarray | None = None, reminded=frozenset(), n: int = N_SIMS, seed: int = SEED,
             deterministic: bool = False, fails=frozenset(), pulled: dict | None = None, at_days: tuple[int, ...] = (), low_quantiles: bool = False) -> dict:
    """`extra` is a cumulative balance change per day (index 0 = today) from moves other than collecting and discounts.
    `fails`: customers assumed never to pay (for Plan B). `pulled`: invoice id -> (day, share kept) offered an early-payment discount."""
    rng = np.random.default_rng(seed)
    n = 1 if deterministic else n
    p = _paths(m, n, extra, frozenset(reminded), rng, deterministic, frozenset(fails), pulled)
    lows = p.min(axis=1)
    neg = p < 0
    first_neg = np.where(neg.any(axis=1), neg.argmax(axis=1), -1)
    short = first_neg[first_neg >= 0]
    dates = [str((m.as_of + pd.Timedelta(days=int(i))).date()) for i in range(m.horizon + 1)]
    weekly = list(range(0, m.horizon + 1, 7))
    if weekly[-1] != m.horizon:
        weekly.append(m.horizon)
    q = np.percentile(p[:, weekly], [10, 50, 90], axis=0)
    return {
        "sims": int(n),
        "p_safe": round(float((lows >= safety).mean()), 3),
        "p_short": round(float((lows < 0).mean()), 3),
        "typical_short_date": dates[int(np.median(short))] if len(short) else None,
        "bad_case_lowest": money(float(np.percentile(lows, 10))),
        "median_lowest": money(float(np.median(lows))),
        "band": [{"date": dates[i], "p10": money(q[0][k]), "p50": money(q[1][k]), "p90": money(q[2][k])} for k, i in enumerate(weekly)],
        "at": {d: tuple(money(x) for x in np.percentile(p[:, d], [10, 50, 90])) for d in at_days if d <= m.horizon},
        **({"low_p10": money(float(np.percentile(lows, 10))), "low_p90": money(float(np.percentile(lows, 90)))} if low_quantiles else {}),
        "_paths": p if deterministic else None,
    }


def assumptions(m: Model) -> list[str]:
    return [
        f"{N_SIMS:,} simulated futures. Customer payment dates are drawn from {m.history_points} past payments (paid date minus due date); "
        "customers with fewer than 3 past payments use everyone's history.",
        f"Overdue up to 30 days: paid within the 90 days in {LATE_PAY_PROB:.0%} of futures ({REMINDED_LATE_PAY_PROB:.0%} after a reminder, within 1–2 weeks).",
        f"More than 30 days late: paid in {STUCK_PAY_PROB:.0%} of futures, {REMINDED_PAY_PROB:.0%} after a reminder (within 1–3 weeks)"
        + (" — updated per customer from how they responded to past reminders: " + ", ".join(f"{k} {v:.0%}" for k, v in m.reminder_p.items()) if m.reminder_p else "") + ".",
        f"An early-payment discount offer is accepted in {DISCOUNT_ACCEPT_PROB:.0%} of futures.",
        f"Typical sales vary month to month by about {m.cv_in:.0%} and typical costs by about {m.cv_out:.0%}, as they did over the last 6 months.",
        "Bills, salaries, rent and taxes are paid on their due dates in every future.",
    ]
