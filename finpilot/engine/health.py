"""
Business health score (0–100) from five plain checks, each worth 20 points:

  cash cushion   months of running costs covered by today's bank balance
  profit         estimated operating margin over the last 3 full months
  collections    share of what customers owe that is overdue
  bills          share of what you owe suppliers that is overdue
  momentum       sales in the last 3 full months vs the 3 before

Each check maps a measured value to points with a fixed, documented scale (linear between the
anchor points below), so the score is reproducible and explainable — not a credit score, and not
a prediction. A check that can't be measured (e.g. no balance) scores 0 and says what's missing,
except collections/bills with no invoices at all, which score a neutral 12.
"""

from __future__ import annotations

import pandas as pd

from finpilot.data.schema import Evidence
from finpilot.engine.cash import cash_position, obligations_status
from finpilot.engine.common import last_full_month, ts
from finpilot.engine.decision import default_buffer
from finpilot.engine.summary import financial_summary

NEUTRAL = 12

# (value, points) anchors; linear in between, clamped at the ends.
SCALES = {
    "cash": [(0, 0), (0.5, 6), (1, 11), (2, 16), (3, 20)],          # months of costs
    "profit": [(-10, 0), (0, 6), (10, 13), (20, 18), (25, 20)],      # margin %
    "collections": [(0, 20), (10, 17), (25, 11), (50, 4), (75, 0)],  # % of receivables overdue
    "bills": [(0, 20), (10, 15), (25, 8), (50, 0)],                  # % of payables overdue
    "momentum": [(-25, 0), (-10, 7), (0, 13), (10, 18), (20, 20)],   # % sales change
}


def points(key: str, value: float) -> float:
    pts = SCALES[key]
    if value <= pts[0][0]:
        return float(pts[0][1])
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if value <= x1:
            return round(y0 + (y1 - y0) * (value - x0) / (x1 - x0), 1)
    return float(pts[-1][1])


def _status(p: float) -> str:
    return "good" if p >= 15 else "caution" if p >= 8 else "bad"


def obligations_as_of(obligations, d):
    """What the invoices and bills looked like on date d: only those issued by then, and unpaid if paid later."""
    if obligations is None or not len(obligations):
        return obligations
    o = obligations.copy()
    for c in ("issue_date", "due_date", "paid_date"):
        o[c] = pd.to_datetime(o[c])
    o = o[o["issue_date"].isna() | (o["issue_date"] <= d)]
    later = (o["status"] == "paid") & (o["paid_date"].isna() | (o["paid_date"] > d)) & o["paid_date"].notna()
    o.loc[later, "status"] = "pending"
    return o


def _quarter_sales(ledger, end) -> float | None:
    start = (end - pd.DateOffset(months=2)).replace(day=1)
    s = financial_summary(ledger, start, end)
    return s["revenue"] if s["status"] == "ok" else None


def health_score(ledger: pd.DataFrame, balances, obligations, as_of, with_history: bool = True) -> dict:
    a = ts(as_of)
    comps = []

    pos = cash_position(ledger, balances, a)
    buf = default_buffer(ledger, a)
    if pos["status"] != "ok":
        comps.append({"key": "cash", "value": None, "points": 0.0, "status": "unknown"})
    elif not buf:
        comps.append({"key": "cash", "value": None, "points": float(NEUTRAL), "status": "unknown"})
    else:
        months = pos["cash_balance"] / buf
        comps.append({"key": "cash", "value": round(months, 1), "points": points("cash", months), "status": None})

    _, m_end = last_full_month(a)
    q_start = (m_end - pd.DateOffset(months=2)).replace(day=1)
    s = financial_summary(ledger, q_start, m_end)
    if s["status"] == "ok" and s["revenue"] > 0:
        comps.append({"key": "profit", "value": round(s["estimated_margin_pct"], 1), "points": points("profit", s["estimated_margin_pct"]), "status": None})
    else:
        comps.append({"key": "profit", "value": None, "points": 0.0, "status": "unknown"})

    obl = obligations_status(obligations_as_of(obligations, a), a)
    for key, side in (("collections", "receivables"), ("bills", "payables")):
        if obl["status"] != "ok":
            comps.append({"key": key, "value": None, "points": float(NEUTRAL), "status": "unknown"})
            continue
        part = obl[side]
        total = part["pending_not_due"] + part["overdue"]
        if total <= 0:
            comps.append({"key": key, "value": 0.0, "points": 20.0, "status": None})
        else:
            pct = part["overdue"] / total * 100
            comps.append({"key": key, "value": round(pct, 1), "points": points(key, pct), "status": None})

    now_q = _quarter_sales(ledger, m_end)
    prev_end = q_start - pd.Timedelta(days=1)
    prev_q = _quarter_sales(ledger, prev_end)
    if now_q is not None and prev_q:
        ch = (now_q - prev_q) / prev_q * 100
        comps.append({"key": "momentum", "value": round(ch, 1), "points": points("momentum", ch), "status": None})
    else:
        comps.append({"key": "momentum", "value": None, "points": float(NEUTRAL), "status": "unknown"})

    for c in comps:
        c["status"] = c["status"] or _status(c["points"])
        c["max"] = 20
    score = int(round(sum(c["points"] for c in comps)))
    grade = "Excellent" if score >= 80 else "Good" if score >= 65 else "Fair" if score >= 45 else "Needs attention"
    out = {
        "status": "ok",
        "score": score,
        "grade": grade,
        "components": comps,
        "evidence": Evidence(
            method="Five checks worth 20 points each, using fixed scales: cash cushion (months of running costs in the bank), "
                   "estimated operating margin over the last 3 full months, % of customer dues overdue, % of supplier bills overdue, "
                   "and sales in the last 3 full months vs the 3 before.",
            assumptions=("Checks that can't be measured from your data score neutral (12) or zero, as labelled.",),
            limitations=("A summary of your own records — not a credit score and not a prediction.",),
            period=(str(q_start.date()), str(m_end.date())),
        ).to_dict(),
    }
    if with_history:
        first = pd.to_datetime(ledger["date"]).min() if len(ledger) else a
        prev_end = a.replace(day=1) - pd.Timedelta(days=1)
        hist = []
        for k in range(4, -1, -1):
            me = ((prev_end - pd.DateOffset(months=k)) + pd.offsets.MonthEnd(0)).normalize()
            if me < first + pd.Timedelta(days=90):  # needs a few months of history to mean anything
                continue
            hist.append({"month": me.strftime("%b"), "date": str(me.date()), "score": health_score(ledger, balances, obligations, me, with_history=False)["score"]})
        hist.append({"month": a.strftime("%b"), "date": str(a.date()), "score": score})
        out["history"] = hist
    return out
