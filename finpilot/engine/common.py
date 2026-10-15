"""Shared helpers for the financial engine. Every number FinPilot reports comes from this package."""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd

from finpilot.data.schema import classify


def ts(value: date | datetime | str | pd.Timestamp | None) -> pd.Timestamp | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return pd.Timestamp(value).normalize()


def money(x: float) -> float:
    """Round to paise; avoids -0.0."""
    v = round(float(x), 2)
    return 0.0 if v == 0 else v


def prepare_ledger(ledger: pd.DataFrame) -> pd.DataFrame:
    """Add the accounting class and a signed amount (inflows +, outflows −)."""
    df = ledger.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    df["cls"] = [classify(c, d) for c, d in zip(df["category"], df["direction"])]
    df["signed"] = df["amount"].where(df["direction"] == "in", -df["amount"])
    return df


def in_period(df: pd.DataFrame, start=None, end=None, col: str = "date") -> pd.DataFrame:
    s, e = ts(start), ts(end)
    mask = pd.Series(True, index=df.index)
    if s is not None:
        mask &= df[col] >= s
    if e is not None:
        mask &= df[col] <= e
    return df[mask]


def fmt_inr(x: float) -> str:
    """₹ with Indian digit grouping (12,34,567.50 → ₹12,34,568)."""
    neg = x < 0
    n = int(round(abs(x)))
    s = str(n)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    return f"{'−' if neg else ''}₹{s}"


def month_end(d: pd.Timestamp) -> pd.Timestamp:
    return (d + pd.offsets.MonthEnd(0)).normalize()


def last_full_month(as_of) -> tuple[pd.Timestamp, pd.Timestamp]:
    """The last complete calendar month on or before as_of."""
    a = ts(as_of)
    if a == month_end(a):
        return a.replace(day=1), a
    end = (a.replace(day=1) - pd.Timedelta(days=1)).normalize()
    return end.replace(day=1), end
