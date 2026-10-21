"""
Track record: how good would FinPilot's forecasts and odds have been, on this business's own past?

For each week in the past (with at least 3 full months of history before it and 30 days of history after it):
  1. rewind the books to that day — only transactions up to then, invoices and bills as they stood then
     (issued by then; paid only if paid by then)
  2. forecast 30 days ahead exactly as the app does today, and play out the 1,000 simulated futures
  3. compare with what actually happened in the next 30 days

Reported:
  error         |forecast balance − actual| at day 30, against a "the balance stays where it is" guess
  range         how often the actual day-30 balance fell inside the 10–90% range of the simulated futures (ideal ≈ 80%)
  odds          Brier score of "chance you stay above the cushion" against what happened (0 = perfect, 0.25 = coin flip)
  dips          weeks where cash really went below the cushion within 30 days, and how many were flagged in advance

Nothing here is tuned to the answers: the forecast and simulation code are the same ones the app uses.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from finpilot.engine import autopilot as ap
from finpilot.engine import risk
from finpilot.engine.cash import cash_position
from finpilot.engine.common import money, prepare_ledger, ts

HORIZON = 30


def rewind(ledger: pd.DataFrame, obligations: pd.DataFrame | None, balances: pd.DataFrame | None, when) -> tuple:
    t = ts(when)
    led = ledger[pd.to_datetime(ledger["date"]) <= t].copy()
    bal = None if balances is None else balances[pd.to_datetime(balances["as_of"]) <= t].copy()
    obl = None
    if obligations is not None and len(obligations):
        o = obligations.copy()
        for c in ("issue_date", "due_date", "paid_date"):
            o[c] = pd.to_datetime(o[c])
        issued = o["issue_date"].fillna(o["due_date"] - pd.Timedelta(days=30))
        o = o[issued <= t].copy()
        later = o["paid_date"].notna() & (o["paid_date"] > t)
        o.loc[later, "status"] = "pending"
        o.loc[later, "paid_date"] = pd.NaT
        obl = o
    return led, obl, bal


def _actual_path(ledger: pd.DataFrame, start_cash: float, when, days: int) -> np.ndarray:
    t = ts(when)
    df = prepare_ledger(ledger)
    win = df[(df["date"] > t) & (df["date"] <= t + pd.Timedelta(days=days))]
    per_day = win.groupby("date")["signed"].sum().reindex(pd.date_range(t + pd.Timedelta(days=1), t + pd.Timedelta(days=days)), fill_value=0.0)
    return np.concatenate([[start_cash], start_cash + per_day.cumsum().to_numpy()])


def run(ledger: pd.DataFrame, obligations: pd.DataFrame | None, balances: pd.DataFrame | None, sims: int = 500) -> dict:
    led_all = ledger.copy()
    led_all["date"] = pd.to_datetime(led_all["date"])
    first, last = led_all["date"].min(), led_all["date"].max()
    start = (first + pd.DateOffset(months=3)).normalize()
    start = start + pd.Timedelta(days=(7 - start.weekday()) % 7)  # Mondays
    end = last - pd.Timedelta(days=HORIZON)
    points = []
    for when in pd.date_range(start, end, freq="7D"):
        led, obl, bal = rewind(led_all, obligations, balances, when)
        pos = cash_position(led, bal, when)
        if pos["status"] != "ok":
            continue
        safety = ap.default_safety(led, when)
        obl_r, _ = ap.at_risk(obl, when)
        f = ap._forecast(led, bal, obl_r, when, HORIZON, safety)
        if f["status"] != "ok":
            continue
        model = risk.build(led, obl, when, f, ap.stuck_parties(obl, when))
        sim = risk.simulate(model, safety, n=sims, at_days=(HORIZON,), low_quantiles=True)
        actual = _actual_path(led_all, float(pos["cash_balance"]), when, HORIZON)
        pred = np.array([d["balance"] for d in f["daily"]])
        p10, p50, p90 = sim["at"][HORIZON]
        flagged = f["lowest_balance"] < safety or sim["p_safe"] < ap.TARGET_ODDS
        dipped = bool(actual.min() < safety)
        points.append({
            "date": str(when.date()), "cash": money(actual[0]), "safety": safety,
            "forecast_30": money(pred[-1]), "actual_30": money(actual[-1]), "flat_30": money(actual[0]),
            "error": money(abs(pred[-1] - actual[-1])), "flat_error": money(abs(actual[0] - actual[-1])),
            "p10": money(p10), "p90": money(p90), "inside": bool(p10 <= actual[-1] <= p90),
            "p_safe": sim["p_safe"], "stayed_safe": not dipped, "flagged": bool(flagged), "dipped": dipped,
            "actual_lowest": money(actual.min()), "forecast_lowest": f["lowest_balance"],
            "low_error": money(abs(f["lowest_balance"] - actual.min())), "flat_low_error": money(abs(actual[0] - actual.min())),
            "path_error": money(float(np.mean(np.abs(pred[1:] - actual[1:])))), "flat_path_error": money(float(np.mean(np.abs(actual[0] - actual[1:])))),
            "low_inside": bool(sim["low_p10"] <= actual.min() <= sim["low_p90"]),
        })
    return summarise(points)


def summarise(points: list[dict]) -> dict:
    if not points:
        return {"status": "insufficient_data", "message": "Track record needs at least 4 months of transactions.", "points": []}
    err = np.array([p["error"] for p in points])
    flat = np.array([p["flat_error"] for p in points])
    cash = np.array([max(abs(p["cash"]), 1.0) for p in points])
    def better(a, b):
        return round(float(1 - np.median(a) / np.median(b)), 3) if np.median(b) > 0 else None

    low = np.array([p["low_error"] for p in points])
    flat_low = np.array([p["flat_low_error"] for p in points])
    path = np.array([p["path_error"] for p in points])
    flat_path = np.array([p["flat_path_error"] for p in points])
    brier = float(np.mean([(p["p_safe"] - (1.0 if p["stayed_safe"] else 0.0)) ** 2 for p in points]))
    dips = [p for p in points if p["dipped"]]
    flags = [p for p in points if p["flagged"]]
    buckets = []
    for lo, hi in ((0, 0.2), (0.2, 0.5), (0.5, 0.8), (0.8, 1.01)):
        b = [p for p in points if lo <= p["p_safe"] < hi]
        if b:
            buckets.append({"range": [lo, min(hi, 1.0)], "weeks": len(b), "said": round(float(np.mean([p["p_safe"] for p in b])), 3),
                            "happened": round(float(np.mean([p["stayed_safe"] for p in b])), 3)})
    return {
        "status": "ok",
        "weeks": len(points),
        "period": [points[0]["date"], points[-1]["date"]],
        "horizon_days": HORIZON,
        "median_error": money(float(np.median(err))),
        "median_flat_error": money(float(np.median(flat))),
        "median_error_pct_of_cash": round(float(np.median(err / cash)), 3),
        "better_than_flat_pct": round(float(1 - np.median(err) / np.median(flat)), 3) if np.median(flat) > 0 else None,
        "weeks_beating_flat": int(np.sum(err < flat)),
        "range_coverage": round(float(np.mean([p["inside"] for p in points])), 3),
        "median_low_error": money(float(np.median(low))), "median_flat_low_error": money(float(np.median(flat_low))),
        "low_better_than_flat_pct": better(low, flat_low),
        "median_path_error": money(float(np.median(path))), "median_flat_path_error": money(float(np.median(flat_path))),
        "path_better_than_flat_pct": better(path, flat_path),
        "low_range_coverage": round(float(np.mean([p["low_inside"] for p in points])), 3),
        "brier": round(brier, 3),
        "calibration": buckets,
        "dips": len(dips),
        "dips_flagged": sum(p["flagged"] for p in dips),
        # how far below the cushion the missed dips went (small = near misses)
        "missed_dip_depth": money(max((p["safety"] - p["actual_lowest"] for p in dips if not p["flagged"]), default=0.0)),
        "flags": len(flags),
        "false_alarms": sum(not p["dipped"] for p in flags),
        "points": points,
    }
