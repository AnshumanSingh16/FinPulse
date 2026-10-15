"""
The approved tools the orchestrating agent may call.

Each tool has (1) a JSON schema the model sees, (2) a Python validator that checks and normalises
the arguments before anything runs, and (3) an implementation that calls the tested financial
engine. Tools never compute in the model: every figure in a result comes from finpilot.engine.
Results are trimmed for the model (no day-by-day series, capped record lists) but keep their
evidence: method, assumptions, limitations and supporting record ids.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable

import pandas as pd

from finpilot.data import store
from finpilot.engine.cash import cash_position, obligations_status, upcoming_payments
from finpilot.engine.decision import Purchase, simulate_purchase
from finpilot.engine.expenses import compare_expenses, default_periods, unusual_transactions
from finpilot.engine.forecast import ForecastOptions, forecast_cash_flow
from finpilot.engine.summary import financial_summary


class ToolArgumentError(ValueError):
    """The model sent arguments that fail validation. Returned to it as an error result."""


@dataclass
class ToolContext:
    ledger: pd.DataFrame
    obligations: pd.DataFrame | None
    balances: pd.DataFrame | None
    as_of: pd.Timestamp
    db_path: Any = None  # where proposed actions are queued


# ---------------------------------------------------------------- validation helpers

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _date(args: dict, key: str, required: bool = False) -> str | None:
    v = args.get(key)
    if v in (None, ""):
        if required:
            raise ToolArgumentError(f"'{key}' is required (YYYY-MM-DD).")
        return None
    if not isinstance(v, str) or not _DATE.match(v):
        raise ToolArgumentError(f"'{key}' must be a date as YYYY-MM-DD, got {v!r}.")
    try:
        date.fromisoformat(v)
    except ValueError as e:
        raise ToolArgumentError(f"'{key}' is not a real date: {v}.") from e
    return v


def _num(args: dict, key: str, lo: float | None = None, hi: float | None = None, default=None, required=False, integer=False):
    v = args.get(key, default)
    if v is None:
        if required:
            raise ToolArgumentError(f"'{key}' is required.")
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ToolArgumentError(f"'{key}' must be a number, got {v!r}.")
    if integer and int(v) != v:
        raise ToolArgumentError(f"'{key}' must be a whole number.")
    if lo is not None and v < lo or hi is not None and v > hi:
        raise ToolArgumentError(f"'{key}' must be between {lo} and {hi}, got {v}.")
    return int(v) if integer else float(v)


def _bool(args: dict, key: str, default: bool) -> bool:
    v = args.get(key, default)
    if not isinstance(v, bool):
        raise ToolArgumentError(f"'{key}' must be true or false.")
    return v


def _str(args: dict, key: str, max_len: int = 200, required: bool = False, choices=None) -> str | None:
    v = args.get(key)
    if v in (None, ""):
        if required:
            raise ToolArgumentError(f"'{key}' is required.")
        return None
    if not isinstance(v, str) or len(v) > max_len:
        raise ToolArgumentError(f"'{key}' must be text of at most {max_len} characters.")
    if choices and v not in choices:
        raise ToolArgumentError(f"'{key}' must be one of {', '.join(choices)}.")
    return v.strip()


def _reject_unknown(args: dict, allowed: set[str]) -> None:
    extra = set(args) - allowed
    if extra:
        raise ToolArgumentError(f"Unknown argument(s): {', '.join(sorted(extra))}.")


def _trim_evidence(ev: dict, max_ids: int = 25) -> dict:
    ids = ev.get("record_ids") or []
    out = dict(ev)
    out["record_ids"] = ids[:max_ids]
    out["record_count"] = len(ids)
    if len(ids) > max_ids:
        out["record_ids_note"] = f"{len(ids) - max_ids} more record ids not shown; use get_supporting_records for specific ones."
    return out


def _as_of_or(ctx: ToolContext, v: str | None) -> pd.Timestamp:
    if v is None:
        return ctx.as_of
    d = pd.Timestamp(v)
    if d > ctx.as_of:
        raise ToolArgumentError(f"Dates after the data's as-of date ({ctx.as_of.date()}) are in the future; use forecast_cash_flow instead.")
    return d


# ---------------------------------------------------------------- tools


def t_summary(ctx: ToolContext, a: dict) -> dict:
    _reject_unknown(a, {"start_date", "end_date"})
    start, end = _date(a, "start_date"), _date(a, "end_date")
    r = financial_summary(ctx.ledger, start, end or str(ctx.as_of.date()), ctx.obligations, ctx.as_of)
    if r["status"] == "ok":
        r["evidence"] = _trim_evidence(r["evidence"])
    return r


def t_expense_changes(ctx: ToolContext, a: dict) -> dict:
    _reject_unknown(a, {"period_a_start", "period_a_end", "period_b_start", "period_b_end", "months"})
    dates = [_date(a, k) for k in ("period_a_start", "period_a_end", "period_b_start", "period_b_end")]
    months = _num(a, "months", 1, 12, default=1, integer=True)
    if any(dates) and not all(dates):
        raise ToolArgumentError("Give all four period dates, or none to compare the last full month(s) with the ones before.")
    if all(dates):
        pa, pb = (dates[0], dates[1]), (dates[2], dates[3])
        if dates[0] > dates[1] or dates[2] > dates[3]:
            raise ToolArgumentError("Each period's start must be on or before its end.")
    else:
        pa, pb = default_periods(ctx.as_of, months)
    r = compare_expenses(ctx.ledger, pa, pb)
    if r["status"] == "ok":
        r["evidence"] = _trim_evidence(r["evidence"])
    return r


def t_unusual(ctx: ToolContext, a: dict) -> dict:
    _reject_unknown(a, {"lookback_days"})
    days = _num(a, "lookback_days", 7, 365, default=90, integer=True)
    return unusual_transactions(ctx.ledger, ctx.as_of, lookback_days=days)


def t_cash(ctx: ToolContext, a: dict) -> dict:
    _reject_unknown(a, {"as_of_date"})
    d = _as_of_or(ctx, _date(a, "as_of_date"))
    r = cash_position(ctx.ledger, ctx.balances, d)
    if r["status"] == "ok":
        r["evidence"] = _trim_evidence(r["evidence"])
    return r


def t_owed(ctx: ToolContext, a: dict) -> dict:
    _reject_unknown(a, set())
    r = obligations_status(ctx.obligations, ctx.as_of)
    if r["status"] == "ok":
        for k in ("receivables", "payables"):
            r[k]["outstanding"] = round(r[k]["pending_not_due"] + r[k]["overdue"], 2)
    return r


def t_upcoming(ctx: ToolContext, a: dict) -> dict:
    _reject_unknown(a, {"days"})
    days = _num(a, "days", 1, 180, default=30, integer=True)
    return upcoming_payments(ctx.obligations, ctx.as_of, days)


def t_forecast(ctx: ToolContext, a: dict) -> dict:
    _reject_unknown(a, {"horizon_days", "include_typical_unscheduled_flows", "include_overdue_receivables", "receivable_delay_days", "receivable_collection_pct", "min_buffer"})
    opt = ForecastOptions(
        horizon_days=_num(a, "horizon_days", 7, 365, default=90, integer=True),
        include_run_rate=_bool(a, "include_typical_unscheduled_flows", True),
        include_overdue_receivables=_bool(a, "include_overdue_receivables", False),
        receivable_delay_days=_num(a, "receivable_delay_days", 0, 180, default=0, integer=True),
        receivable_collection_pct=_num(a, "receivable_collection_pct", 0, 100, default=100),
        min_buffer=_num(a, "min_buffer", 0, 1e11),
    )
    r = forecast_cash_flow(ctx.ledger, ctx.balances, ctx.obligations, ctx.as_of, opt)
    if r["status"] == "ok":
        r.pop("daily", None)
        items = r.pop("scheduled_items")
        r["scheduled_items_count"] = len(items)
        r["largest_scheduled_items"] = sorted(items, key=lambda i: -abs(i["amount"]))[:12]
        r["excluded_total"] = round(sum(e["amount"] for e in r.get("excluded_items", [])), 2)
        r["evidence"] = _trim_evidence(r["evidence"])
    return r


def t_purchase(ctx: ToolContext, a: dict) -> dict:
    _reject_unknown(a, {"name", "cost", "purchase_date", "financing", "down_payment_pct", "loan_rate_pct", "tenure_months", "monthly_benefit", "benefit_start_months", "monthly_running_cost", "one_time_costs", "horizon_days", "min_buffer"})
    financing = _str(a, "financing", choices=("cash", "loan")) or "cash"
    p = Purchase(
        name=_str(a, "name", 80, required=True),
        cost=_num(a, "cost", 1, 1e10, required=True),
        purchase_date=_date(a, "purchase_date") or str(ctx.as_of.date()),
        financing=financing,
        down_payment_pct=_num(a, "down_payment_pct", 0, 99.99, default=20) if financing == "loan" else 100.0,
        loan_rate_pct=_num(a, "loan_rate_pct", 0, 40, default=None) if financing == "loan" else 0.0,
        tenure_months=_num(a, "tenure_months", 1, 360, default=None, integer=True) if financing == "loan" else 12,
        monthly_benefit=_num(a, "monthly_benefit", 0, 1e9, default=0),
        benefit_start_months=_num(a, "benefit_start_months", 0, 36, default=1, integer=True),
        monthly_running_cost=_num(a, "monthly_running_cost", 0, 1e9, default=0),
        one_time_costs=_num(a, "one_time_costs", 0, 1e10, default=0),
    )
    if financing == "loan" and (p.loan_rate_pct is None or p.tenure_months is None):
        missing = [k for k, v in (("loan_rate_pct", p.loan_rate_pct), ("tenure_months", p.tenure_months)) if v is None]
        return {"status": "needs_input", "message": "To check a loan, the interest rate and loan length from the lender's quote are needed. FinPilot does not assume loan terms.", "missing": missing}
    r = simulate_purchase(
        ctx.ledger, ctx.balances, ctx.obligations, ctx.as_of, p,
        horizon_days=_num(a, "horizon_days", 30, 730, default=180, integer=True),
        min_buffer=_num(a, "min_buffer", 0, 1e11),
    )
    if r["status"] == "ok":
        for s in r["scenarios"]:
            s.pop("daily_with", None)
            s.pop("daily_without", None)
        if not p.monthly_benefit:
            r.setdefault("notes", []).append("No expected monthly benefit was given, so none is counted.")
    return r


def t_records(ctx: ToolContext, a: dict) -> dict:
    _reject_unknown(a, {"record_ids"})
    ids = a.get("record_ids")
    if not isinstance(ids, list) or not ids or not all(isinstance(i, str) for i in ids):
        raise ToolArgumentError("'record_ids' must be a non-empty list of ids (e.g. T0123, INV-0099).")
    if len(ids) > 50:
        raise ToolArgumentError("Ask for at most 50 records at a time.")
    led = ctx.ledger[ctx.ledger["txn_id"].isin(ids)]
    obl = ctx.obligations[ctx.obligations["item_id"].isin(ids)] if ctx.obligations is not None else pd.DataFrame()

    def rows(df):
        out = df.copy()
        for c in out.columns:
            if pd.api.types.is_datetime64_any_dtype(out[c]):
                out[c] = out[c].dt.strftime("%Y-%m-%d")
        return out.where(pd.notna(out), None).to_dict(orient="records")

    found = set(led["txn_id"]) | (set(obl["item_id"]) if len(obl) else set())
    return {
        "status": "ok",
        "transactions": rows(led),
        "invoices_and_bills": rows(obl) if len(obl) else [],
        "not_found": [i for i in ids if i not in found],
    }


def t_propose(ctx: ToolContext, a: dict) -> dict:
    _reject_unknown(a, {"action", "reason", "details"})
    action = _str(a, "action", 120, required=True)
    reason = _str(a, "reason", 400, required=True)
    details = a.get("details") or {}
    if not isinstance(details, dict):
        raise ToolArgumentError("'details' must be an object.")
    if ctx.db_path is None:
        return {"status": "not_recorded", "message": "No approval queue is available in this context."}
    item = store.propose_action(ctx.db_path, action, {"reason": reason, **details})
    return {
        "status": "awaiting_human_approval",
        "approval_id": item,
        "message": "Recorded in the approval queue. Nothing has been sent, paid or filed — a person must approve it, and even then FinPilot has no integration that executes it.",
    }


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    schema: dict
    run: Callable[[ToolContext, dict], dict]


def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or [], "additionalProperties": False}


D = {"type": "string", "description": "YYYY-MM-DD"}
TOOLS: list[Tool] = [
    Tool(
        "get_financial_summary",
        "Revenue (cash basis), recorded operating expenses, ESTIMATED operating profit and net cash movement for a period, with monthly figures, expenses by category, and flows outside operating profit (asset purchases, loans, drawings, taxes). Defaults to all data up to the as-of date.",
        _obj({"start_date": D, "end_date": D}),
        t_summary,
    ),
    Tool(
        "analyze_expense_changes",
        "Compare operating expenses by category between two periods (A earlier, B later), with the largest transactions behind each change. With no dates: the last `months` full month(s) vs the same number before them.",
        _obj({"period_a_start": D, "period_a_end": D, "period_b_start": D, "period_b_end": D, "months": {"type": "integer", "minimum": 1, "maximum": 12}}),
        t_expense_changes,
    ),
    Tool(
        "find_unusual_transactions",
        "Flag possible duplicate payments, outlier expenses (far above the category's usual amount) and rare large payments in the last N days.",
        _obj({"lookback_days": {"type": "integer", "minimum": 7, "maximum": 365}}),
        t_unusual,
    ),
    Tool(
        "get_cash_position",
        "The actual bank cash on a date, from the latest dated balance plus later ledger movements, with reconciliation against statement balances. Returns status 'unknown' if no dated balance exists — never estimate cash from revenue minus expenses.",
        _obj({"as_of_date": D}),
        t_cash,
    ),
    Tool(
        "get_receivables_and_payables",
        "Amounts customers owe and amounts owed to suppliers: paid, pending (not yet due) and overdue, with overdue items and ageing.",
        _obj({}),
        t_owed,
    ),
    Tool(
        "get_upcoming_payments",
        "Bills due in the next N days, plus any already overdue.",
        _obj({"days": {"type": "integer", "minimum": 1, "maximum": 180}}),
        t_upcoming,
    ),
    Tool(
        "forecast_cash_flow",
        "Project the bank balance forward (checkpoints at 30/60/90 days and the horizon) from today's cash, scheduled receivables and payables, and optionally typical unscheduled flows from recent months. An assumption-based projection, not a prediction; returns its assumptions and limitations.",
        _obj(
            {
                "horizon_days": {"type": "integer", "minimum": 7, "maximum": 365},
                "include_typical_unscheduled_flows": {"type": "boolean", "description": "Add average recent flows for costs/sales without uploaded bills or invoices (default true)."},
                "include_overdue_receivables": {"type": "boolean", "description": "Count overdue customer payments as arriving in 30 days (default false)."},
                "receivable_delay_days": {"type": "integer", "minimum": 0, "maximum": 180},
                "receivable_collection_pct": {"type": "number", "minimum": 0, "maximum": 100},
                "min_buffer": {"type": "number", "minimum": 0, "description": "Cash level to warn below, ₹."},
            }
        ),
        t_forecast,
    ),
    Tool(
        "simulate_purchase",
        "Simulate buying something: its cash impact under base, optimistic and downside scenarios, with and without the purchase, against a cash buffer. For a loan, loan_rate_pct and tenure_months must come from the user — never assume them.",
        _obj(
            {
                "name": {"type": "string"},
                "cost": {"type": "number", "minimum": 1, "description": "Price in ₹."},
                "purchase_date": D,
                "financing": {"type": "string", "enum": ["cash", "loan"]},
                "down_payment_pct": {"type": "number", "minimum": 0, "maximum": 99.99},
                "loan_rate_pct": {"type": "number", "minimum": 0, "maximum": 40},
                "tenure_months": {"type": "integer", "minimum": 1, "maximum": 360},
                "monthly_benefit": {"type": "number", "minimum": 0, "description": "Extra monthly cash the purchase brings (user's estimate)."},
                "benefit_start_months": {"type": "integer", "minimum": 0, "maximum": 36},
                "monthly_running_cost": {"type": "number", "minimum": 0},
                "one_time_costs": {"type": "number", "minimum": 0},
                "horizon_days": {"type": "integer", "minimum": 30, "maximum": 730},
                "min_buffer": {"type": "number", "minimum": 0},
            },
            ["name", "cost"],
        ),
        t_purchase,
    ),
    Tool(
        "get_supporting_records",
        "Fetch the actual transactions (T…/U… ids) or invoices and bills (INV-…, BILL-…, SCH-… ids) behind a result, to quote or check them.",
        _obj({"record_ids": {"type": "array", "items": {"type": "string"}, "maxItems": 50}}, ["record_ids"]),
        t_records,
    ),
    Tool(
        "propose_action",
        "Put a suggested real-world action (e.g. 'send a payment reminder to Metro Foods', 'pay BILL-PKG-0926') into the human approval queue. This never performs the action. Use only when the user asks for something to be done.",
        _obj({"action": {"type": "string"}, "reason": {"type": "string"}, "details": {"type": "object"}}, ["action", "reason"]),
        t_propose,
    ),
]
TOOLS_BY_NAME = {t.name: t for t in TOOLS}


def anthropic_tool_specs() -> list[dict]:
    return [{"name": t.name, "description": t.description, "input_schema": t.schema} for t in TOOLS]


def run_tool(ctx: ToolContext, name: str, args: Any) -> tuple[bool, dict]:
    """Validate and run one tool. Returns (ok, result); errors come back as results, not exceptions."""
    tool = TOOLS_BY_NAME.get(name)
    if tool is None:
        return False, {"status": "error", "message": f"Unknown tool '{name}'. Approved tools: {', '.join(TOOLS_BY_NAME)}."}
    if not isinstance(args, dict):
        return False, {"status": "error", "message": "Tool arguments must be a JSON object."}
    try:
        return True, tool.run(ctx, args)
    except ToolArgumentError as e:
        return False, {"status": "invalid_arguments", "message": str(e)}
