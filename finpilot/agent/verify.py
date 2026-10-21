"""
Verification: nothing the agent says is trusted on its own.

1. Tool-result checks — each result is re-derived independently from the raw tables (plain
   sums over rows, not the engine's code path) or checked for internal arithmetic consistency.
2. Answer checks — every rupee amount, percentage, ISO date and record id in the final answer must
   match a tool output (or the user's own message, or the dataset for ids). Anything else is
   flagged as unverified.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

import pandas as pd

from finpilot.data.schema import classify
from finpilot.engine.decision import emi

TOL = 1.0  # rupees: engine figures are rounded to paise, answers to rupees


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


@dataclass
class VerificationReport:
    checks: list[Check] = field(default_factory=list)
    unverified_figures: list[str] = field(default_factory=list)
    unknown_dates: list[str] = field(default_factory=list)
    unknown_ids: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks) and not (self.unverified_figures or self.unknown_dates or self.unknown_ids)

    @property
    def answer_issues(self) -> list[str]:
        out = []
        if self.unverified_figures:
            out.append("figures not found in any tool result: " + ", ".join(self.unverified_figures))
        if self.unknown_dates:
            out.append("dates not found in any tool result: " + ", ".join(self.unknown_dates))
        if self.unknown_ids:
            out.append("record ids that don't exist: " + ", ".join(self.unknown_ids))
        return out

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "checks": [c.__dict__ for c in self.checks],
            "unverified_figures": self.unverified_figures,
            "unknown_dates": self.unknown_dates,
            "unknown_ids": self.unknown_ids,
        }


# ---------------------------------------------------------------- tool-result checks


def _signed(df: pd.DataFrame) -> pd.Series:
    return df["amount"].where(df["direction"] == "in", -df["amount"])


def check_tool_result(name: str, args: dict, result: dict, ledger: pd.DataFrame, balances, obligations) -> list[Check]:
    if not isinstance(result, dict) or result.get("status") not in ("ok",):
        return []
    out: list[Check] = []
    close = lambda a, b: abs(float(a) - float(b)) <= TOL  # noqa: E731

    if name == "get_financial_summary":
        p = result["period"]
        rows = ledger[(pd.to_datetime(ledger["date"]) >= p["start"]) & (pd.to_datetime(ledger["date"]) <= p["end"])]
        rev = sum(r.amount for r in rows.itertuples() if r.direction == "in" and classify(r.category, r.direction) == "revenue")
        tot_in = sum(r.amount for r in rows.itertuples() if r.direction == "in")
        tot_out = sum(r.amount for r in rows.itertuples() if r.direction == "out")
        out.append(Check("revenue re-summed from rows", close(rev, result["revenue"]), f"{rev:,.2f} vs {result['revenue']:,.2f}"))
        out.append(Check("net cash movement = inflows − outflows", close(tot_in - tot_out, result["net_cash_movement"]), f"{tot_in - tot_out:,.2f} vs {result['net_cash_movement']:,.2f}"))
        out.append(Check("profit = revenue − expenses", close(result["revenue"] - result["operating_expenses"], result["estimated_operating_profit"]), "arithmetic"))
        out.append(Check("monthly figures add up to the total", close(sum(m["revenue"] for m in result["monthly"]), result["revenue"]), "Σ monthly revenue"))

    elif name == "analyze_expense_changes":
        cats = result["by_category"]
        out.append(Check("category changes add up to the total change", close(sum(c["change"] for c in cats), result["total_change"]), "Σ change"))
        out.append(Check("period B total re-summed", close(sum(c["period_b"] for c in cats), result["total_b"]), "Σ period B"))

    elif name == "get_cash_position":
        bal = balances.copy()
        bal["as_of"] = pd.to_datetime(bal["as_of"])
        a = pd.Timestamp(result["anchor_balance"]["as_of"])
        anchor = float(bal.loc[bal["as_of"] == a, "balance"].iloc[0])
        d = pd.to_datetime(ledger["date"])
        rows = ledger[(d > a) & (d <= pd.Timestamp(result["as_of"]))]
        cash = anchor + float(_signed(rows).sum())
        out.append(Check("cash re-derived from balance and rows", close(cash, result["cash_balance"]), f"{cash:,.2f} vs {result['cash_balance']:,.2f}"))

    elif name == "get_receivables_and_payables":
        for k in ("receivables", "payables"):
            part = result[k]
            out.append(Check(f"overdue {k} = sum of overdue items", close(sum(i["amount"] for i in part["overdue_items"]), part["overdue"]), "Σ items"))
            pend = obligations[(obligations["kind"] == k[:-1]) & (obligations["status"] == "pending")]
            out.append(Check(f"pending {k} re-summed", close(pend["amount"].sum(), part["pending_not_due"] + part["overdue"]), "Σ rows"))

    elif name == "get_upcoming_payments":
        out.append(Check("upcoming total = sum of items", close(sum(i["amount"] for i in result["upcoming"]), result["upcoming_total"]), "Σ items"))

    elif name == "forecast_cash_flow":
        for c in result["checkpoints"]:
            ok = close(result["starting_cash"] + c["inflows"] - c["outflows"], c["balance"])
            out.append(Check(f"{c['days']}-day balance = start + in − out", ok, f"{c['date']}"))
        out.append(Check("lowest balance is not above any checkpoint", all(result["lowest_balance"] <= c["balance"] + TOL for c in result["checkpoints"]), "ordering"))

    elif name == "simulate_purchase":
        p = result["purchase"]
        if p["financing"] == "loan":
            expected = emi(p["cost"] * (1 - p["down_payment_pct"] / 100), p["loan_rate_pct"], p["tenure_months"])
            out.append(Check("EMI re-computed", close(expected, result["emi"]), f"{expected:,.2f}"))
        for s in result["scenarios"]:
            ok = s["with_purchase"]["lowest_balance"] <= s["without_purchase"]["lowest_balance"] + TOL or p["monthly_benefit"] > 0
            out.append(Check(f"{s['label']}: purchase can't raise the low point without a benefit", ok, "consistency"))

    elif name == "get_customers_and_suppliers":
        kind = "receivable" if result["side"] == "customers" else "payable"
        if obligations is not None and len(obligations):
            pend = obligations[(obligations["kind"] == kind) & (obligations["status"] == "pending")]
            out.append(Check(f"outstanding {result['side']} re-summed from invoices", close(pend["amount"].sum(), result["total_outstanding"]), "Σ rows"))
        out.append(Check("each person's overdue ≤ outstanding", all(p["overdue"] <= p["outstanding"] + TOL for p in result["people"]), "consistency"))

    elif name == "get_health_score":
        out.append(Check("score = sum of the five checks", abs(round(sum(c["points"] for c in result["components"])) - result["score"]) <= 1, "Σ points"))

    elif name == "run_what_if" and result.get("kind") == "price":
        out.append(Check("monthly change = new profit − baseline profit", close(result["new_profit"] - result["baseline"]["profit"], result["monthly_change"]), "arithmetic"))

    elif name == "run_what_if" and result.get("kind") == "loan":
        out.append(Check("EMI re-computed", close(emi(float(args["loan_amount"]), float(args["interest_rate_pct"]), result["months"]), result["emi"]), "formula"))

    elif name == "get_tax_calendar_and_gst":
        for k in ("gst_last_full_month", "gst_this_month_so_far"):
            if k in result:
                g = result[k]
                out.append(Check(f"{k}: payable = output − input credit", close(max(g["output_gst"] - g["input_credit"], 0), g["estimated_payable"]), "arithmetic"))

    elif name == "investigate_sales_change":
        # re-derived from raw rows: sales in each span by plain sums; the causes must add up to the change
        lg = ledger.copy()
        lg["date"] = pd.to_datetime(lg["date"]).dt.normalize()
        is_rev = pd.Series([classify(c, d) == "revenue" for c, d in zip(lg["category"], lg["direction"])], index=lg.index)
        sales = lg[(lg["direction"] == "in") & is_rev]
        for key in ("current", "previous"):
            a_, b_ = (pd.Timestamp(x) for x in result["period"][key])
            got = sales[(sales["date"] >= a_) & (sales["date"] <= b_)]["amount"].sum()
            out.append(Check(f"sales {key} period = sum of sales rows", close(got, result["sales"][key]), f"{got:.2f}"))
        parts = sum(d["amount"] for d in result["drivers"] if not d.get("overlay"))
        out.append(Check("causes add up to the change", close(parts, result["sales"]["change"]), f"{parts:.2f}"))
        mx = result.get("mix")
        if mx:
            named = sum(c["change"] for c in result["customers"])
            out.append(Check("count effect + size effect = named customers' change", close(mx["count_effect"] + mx["size_effect"], named), f"{named:.2f}"))
    elif name == "get_supporting_records":
        ids = set(args.get("record_ids", []))
        got = {r.get("txn_id") for r in result["transactions"]} | {r.get("item_id") for r in result["invoices_and_bills"]}
        out.append(Check("records returned exist and were requested", got <= ids, f"{len(got)} returned"))
    return out


# ---------------------------------------------------------------- answer checks

_NUM = r"\d{1,3}(?:,\d{2,3})*(?:\.\d+)?|\d+(?:\.\d+)?"
_INR = re.compile(rf"(?:₹|rs\.?\s?|inr\s?)\s?(−|-)?({_NUM})\s*(लाख|करोड़|करोड|हज़ार|हजार|lakh|lakhs|lac|crore|cr|k)?(?!\w)", re.I)
_PCT = re.compile(rf"(−|-)?({_NUM})\s?%")
_BARE = re.compile(r"(?<![\w₹.,-])(\d{1,3}(?:,\d{2,3}){1,})(?![\d,])")
_ISO = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_IDS = re.compile(r"\b(T\d{4}|U\d{5}|E\d{5}|INV-\d{3,}(?:-P\d+)?|BILL-[A-Z0-9][A-Z0-9-]*[A-Z0-9]|SCH-\d{3,}|K-\d{4}(?:-P\d+)?)\b")
UNITS = {"lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "crore": 1e7, "cr": 1e7, "k": 1e3, "लाख": 1e5, "करोड़": 1e7, "करोड": 1e7, "हज़ार": 1e3, "हजार": 1e3}


def collect_numbers(obj, out: list[float] | None = None) -> list[float]:
    out = [] if out is None else out
    if isinstance(obj, bool):
        return out
    if isinstance(obj, (int, float)):
        if math.isfinite(obj):
            out.append(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            collect_numbers(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            collect_numbers(v, out)
    elif isinstance(obj, str):
        # Figures inside tool-written text (e.g. "median 15,000") count as tool output too.
        # Dates and record ids are not figures: "2026-09-30" must not vouch for "30%".
        obj = _IDS.sub(" ", _ISO.sub(" ", obj))
        for m in re.finditer(_NUM, obj):
            try:
                out.append(float(m.group(0).replace(",", "")))
            except ValueError:
                pass
    return out


def collect_strings(obj, out: list[str] | None = None) -> list[str]:
    out = [] if out is None else out
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            collect_strings(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            collect_strings(v, out)
    return out


_UNIT_AMT = re.compile(rf"({_NUM})\s*(लाख|करोड़|करोड|हज़ार|हजार|lakh|lakhs|lac|crore|k)(?!\w)", re.I)


def _unit_amounts(text: str) -> list[float]:
    """'₹12 lakh', '1.5 crore', '45k' in free text, as rupees."""
    return [float(m.group(1).replace(",", "")) * UNITS[m.group(2).lower()] for m in _UNIT_AMT.finditer(text or "")]


def _matches(value: float, pool: list[float], tolerance: float) -> bool:
    v = abs(value)
    return any(abs(abs(p) - v) <= tolerance for p in pool)


def verify_answer(answer: str, tool_results: list, user_text: str, known_ids: set[str], extra_dates: set[str] = frozenset()) -> VerificationReport:
    rep = VerificationReport()
    pool = collect_numbers(tool_results) + collect_numbers(user_text) + _unit_amounts(user_text)
    pct_pool = pool + [p * 100 for p in pool if abs(p) <= 1.5]
    spans: list[tuple[int, int]] = []

    for m in _INR.finditer(answer):
        raw, unit = m.group(2), (m.group(3) or "").lower()
        v = float(raw.replace(",", ""))
        if unit:
            decimals = len(raw.split(".")[1]) if "." in raw else 0
            mult = UNITS[unit]
            tol = 0.5 * mult * 10 ** (-decimals) + TOL
            v *= mult
        else:
            tol = TOL + (0.5 if "." not in raw else 0)
        if not _matches(v, pool, tol):
            rep.unverified_figures.append(m.group(0).strip())
        spans.append(m.span())

    for m in _PCT.finditer(answer):
        raw = m.group(2)
        decimals = len(raw.split(".")[1]) if "." in raw else 0
        v = float(raw.replace(",", ""))
        if not _matches(v, pct_pool, 0.5 * 10 ** (-decimals) + 0.01):
            rep.unverified_figures.append(m.group(0).strip())
        spans.append(m.span())

    for m in _BARE.finditer(answer):
        if any(a <= m.start() < b for a, b in spans):
            continue
        v = float(m.group(1).replace(",", ""))
        if not _matches(v, pool, TOL):
            rep.unverified_figures.append(m.group(1))

    strings = " ".join(collect_strings(tool_results)) + " " + user_text
    for d in set(_ISO.findall(answer)):
        if d not in strings and d not in extra_dates:
            rep.unknown_dates.append(d)
    quoted = set(_IDS.findall(strings))  # ids a tool returned (e.g. inside a description) are quotes, not inventions
    for i in set(_IDS.findall(answer)):
        if i not in known_ids and i not in quoted:
            rep.unknown_ids.append(i)
    rep.unverified_figures = list(dict.fromkeys(rep.unverified_figures))
    return rep
