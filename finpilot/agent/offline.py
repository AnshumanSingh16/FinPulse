"""
Rule-based mode, used when no AI key is configured (or the AI call fails).

It recognises the common questions, runs the same approved tools through the same validation and
recording as the AI agent, and writes the answer from templates using only figures the tools
returned. It is labelled as rule-based everywhere it appears — never presented as AI output.
"""

from __future__ import annotations

import re
from typing import Callable

import pandas as pd

from finpilot.data.loader import parse_amount
from finpilot.engine.common import fmt_inr

ToolCaller = Callable[[str, dict], tuple[bool, dict]]

AMOUNT = re.compile(r"(?:₹|rs\.?\s?|inr\s?)?\s?(\d[\d,]*(?:\.\d+)?)\s*(lakh|lakhs|lac|crore|cr|k)?", re.I)
UNIT = {"lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "crore": 1e7, "cr": 1e7, "k": 1e3}
IDS = re.compile(r"\b(T\d{4}|U\d{5}|INV-\d{3,}|BILL-[A-Z0-9-]+|SCH-\d{3,})\b")


def _money(text: str) -> list[float]:
    """₹ amounts in a sentence (₹12 lakh, 12,00,000, 45k). Ignores bare small numbers and percentages."""
    out = []
    for m in AMOUNT.finditer(text):
        raw, unit = m.group(1), (m.group(2) or "").lower()
        tail = text[m.end(): m.end() + 2]
        if "%" in tail:
            continue
        v, _ = parse_amount(raw)
        if v is None:
            continue
        v *= UNIT.get(unit, 1)
        has_symbol = bool(re.match(r"(₹|rs|inr)", m.group(0).strip(), re.I))
        if v >= 1000 or has_symbol or unit:
            out.append(v)
    return out


def _pct(text: str) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)\s?%", text)
    return float(m.group(1)) if m else None


def _months(text: str) -> int | None:
    m = re.search(r"(\d+)\s*(years?|yrs?)", text, re.I)
    if m:
        return int(m.group(1)) * 12
    m = re.search(r"(\d+)\s*(months?|mo)\b", text, re.I)
    return int(m.group(1)) if m else None


def _inr(x) -> str:
    return "—" if x is None else fmt_inr(x)


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {i}" for i in items)


# ---------------------------------------------------------------- intents


def _purchase(q: str, call: ToolCaller, as_of: pd.Timestamp) -> str:
    amounts = _money(q)
    if not amounts:
        return "To simulate a purchase I need its price — for example *“Can I afford a ₹12 lakh packing machine on a loan at 11% for 3 years?”*"
    low = q.lower()
    loan = bool(re.search(r"\b(loan|emi|finance|financ)", low))
    benefit = None
    m = re.search(r"(?:save|saves|earn|earns|bring|brings|extra|more|benefit)[^.₹\d]{0,30}(₹?\s?\d[\d,]*(?:\.\d+)?\s*(?:lakh|k)?)\s*(?:a|per|/|each)?\s*month", low)
    if m:
        b = _money(m.group(1))
        benefit = b[0] if b else None
    cost = max(a for a in amounts if a != benefit) if benefit and len(amounts) > 1 else amounts[0]
    name = "the purchase"
    nm = re.search(r"(?:buy|purchase|afford|get)\s+(?:a|an|the|new)?\s*(?:₹?\s?[\d,.]+\s*(?:lakh|lakhs|crore|cr|k)?\s*)?([a-z][a-z \-]{2,40}?)(?:\s+(?:on|with|for|using|at|that|which|now|next|this)\b|[?.,]|$)", low)
    if nm:
        name = nm.group(1).strip()
    args = {"name": name[:80], "cost": cost, "financing": "loan" if loan else "cash"}
    if loan:
        rate, tenure = _pct(q), _months(q)
        if rate is not None:
            args["loan_rate_pct"] = rate
        if tenure is not None:
            args["tenure_months"] = tenure
        dp = re.search(r"(\d+(?:\.\d+)?)\s?%\s*(?:down|upfront|margin)", low)
        if dp:
            args["down_payment_pct"] = float(dp.group(1))
            if rate == float(dp.group(1)):
                rest = re.sub(r"(\d+(?:\.\d+)?)\s?%\s*(?:down|upfront|margin)", "", q)
                r2 = _pct(rest)
                args.pop("loan_rate_pct", None) if r2 is None else args.update(loan_rate_pct=r2)
    if benefit:
        args["monthly_benefit"] = benefit
    ok_c, cash = call("get_cash_position", {})
    if ok_c and cash.get("status") != "ok":
        return f"**I can't assess affordability yet.** {cash['message']}"
    call("get_upcoming_payments", {"days": 30})
    ok, r = call("simulate_purchase", args)
    if not ok:
        return f"I couldn't run the simulation: {r['message']}"
    if r.get("status") == "needs_input":
        return f"**I need more detail before simulating this loan.** {r['message']} Tell me the annual interest rate and the tenure your lender quoted."
    if r.get("status") != "ok":
        return r.get("message", "The simulation could not run.")
    sc = {s["scenario"]: s for s in r["scenarios"]}
    lines = [
        f"**{r['verdict']}**",
        "",
        f"Buying **{name}** for {_inr(cost)}" + (f" with {args.get('down_payment_pct', 20):g}% down and an EMI of {_inr(r['emi'])}" if loan else " in cash") + f", over the next {r['horizon_days']} days:",
        _bullets(
            [
                f"**{s['label']}** — lowest bank balance {_inr(s['with_purchase']['lowest_balance'])} on {s['with_purchase']['lowest_balance_date']} (without the purchase: {_inr(s['without_purchase']['lowest_balance'])})"
                for s in (sc.get("base"), sc.get("downside"), sc.get("optimistic"))
                if s
            ]
        ),
        f"- Cash buffer used: {_inr(r['buffer'])} ({r['buffer_basis']}).",
        f"- Today's cash: {_inr(cash.get('cash_balance'))}." if ok_c and cash.get("status") == "ok" else "",
    ]
    if r["payback_months"]:
        lines.append(f"- Simple payback: {r['payback_months']:g} months, based on your expected benefit (not verified by FinPilot).")
    elif not benefit:
        lines.append("- No monthly benefit was given, so the simulation counts only the cost. Tell me what it would save or earn each month to include it.")
    if loan and r.get("total_loan_interest"):
        lines.append(f"- Total loan interest over the tenure: {_inr(r['total_loan_interest'])}.")
    lines.append("\nScenarios are illustrations under the stated settings, not predictions. Open the Decision Lab to change them.")
    return "\n".join(x for x in lines if x is not None)


def _forecast(q: str, call: ToolCaller, as_of) -> str:
    ok, cash = call("get_cash_position", {})
    if ok and cash.get("status") != "ok":
        return f"**I can't forecast cash yet.** {cash['message']}"
    days = 90
    m = re.search(r"(\d{2,3})\s*days", q)
    if m and 7 <= int(m.group(1)) <= 365:
        days = int(m.group(1))
    ok1, typical = call("forecast_cash_flow", {"horizon_days": days, "include_typical_unscheduled_flows": True})
    ok2, sched = call("forecast_cash_flow", {"horizon_days": days, "include_typical_unscheduled_flows": False})
    if not ok1 or typical.get("status") != "ok":
        return typical.get("message", "The forecast could not run.")
    cps = typical["checkpoints"]
    lines = [
        f"**Starting from {_inr(typical['starting_cash'])} in the bank on {typical['as_of']}**, with scheduled invoices and bills plus typical recent flows:",
        _bullets([f"{c['days']} days ({c['date']}): {_inr(c['balance'])}" for c in cps]),
        f"- Lowest point: {_inr(typical['lowest_balance'])} on {typical['lowest_balance_date']}.",
    ]
    if typical.get("first_negative_date"):
        lines.append(f"- ⚠ Cash goes negative on {typical['first_negative_date']}.")
    if ok2 and sched.get("status") == "ok":
        lines.append(
            f"\nCounting **only scheduled items** (no typical costs or sales), the {days}-day balance would be {_inr(sched['checkpoints'][-1]['balance'])} — "
            "the gap shows how much the answer depends on the typical-flows assumption."
        )
    if typical.get("excluded_items"):
        lines.append(f"\nOverdue customer payments of {_inr(typical['excluded_total'])} are **not** counted as incoming.")
    lines.append("\nThis is arithmetic on known items and stated assumptions, not a prediction.")
    return "\n".join(lines)


def _expenses(q: str, call: ToolCaller, as_of) -> str:
    months = 3 if re.search(r"quarter|3 months|three months", q, re.I) else 1
    ok, c = call("analyze_expense_changes", {"months": months})
    if not ok or c.get("status") != "ok":
        return c.get("message", "I couldn't compare expenses.")
    ok_u, u = call("find_unusual_transactions", {"lookback_days": 90})
    pa, pb = c["period_a"], c["period_b"]
    direction = "up" if c["total_change"] > 0 else "down"
    lines = [
        f"**Recorded expenses were {_inr(c['total_b'])} from {pb['start']} to {pb['end']}, {direction} {_inr(abs(c['total_change']))}"
        + (f" ({abs(c['total_change_pct']):.1f}%)" if c["total_change_pct"] is not None else "")
        + f" on {pa['start']} to {pa['end']} ({_inr(c['total_a'])}).**",
        "",
        "Biggest changes:",
    ]
    for r in [r for r in c["by_category"] if r["change"]][:4]:
        top = r["largest_in_b"][0] if r["largest_in_b"] else None
        pct = f" ({r['change_pct']:+.1f}%)" if r["change_pct"] is not None else " (new)"
        lines.append(
            f"- **{r['category']}**: {_inr(r['period_a'])} → {_inr(r['period_b'])}{pct}"
            + (f"; largest: {top['description']} {_inr(top['amount'])} on {top['date']} ({top['txn_id']})" if top else "")
        )
    if ok_u and u.get("flags"):
        lines.append("\nWorth checking (last 90 days):")
        for f in u["flags"][:4]:
            lines.append(f"- {f['category']} {_inr(f['amount'])} on {f['date']} ({', '.join(f['txn_ids'])}): {f['reason']}")
    return "\n".join(lines)


def _unusual(q: str, call: ToolCaller, as_of) -> str:
    ok, u = call("find_unusual_transactions", {"lookback_days": 90})
    if not ok:
        return u["message"]
    if not u["flags"]:
        return f"Nothing unusual found between {u['window']['start']} and {u['window']['end']}."
    lines = [f"**{len(u['flags'])} transaction(s) worth checking** between {u['window']['start']} and {u['window']['end']}:"]
    for f in u["flags"]:
        lines.append(f"- **{f['type'].replace('_', ' ')}** — {f['category']}, {f['counterparty']}, {_inr(f['amount'])} on {f['date']} ({', '.join(f['txn_ids'])}). {f['reason']}")
    lines.append("\nA flag is a prompt to check, not a finding of error.")
    return "\n".join(lines)


def _cash(q: str, call: ToolCaller, as_of) -> str:
    ok, c = call("get_cash_position", {})
    if c.get("status") != "ok":
        return f"**Cash position unknown.** {c['message']}"
    lines = [
        f"**Cash in bank on {c['as_of']}: {_inr(c['cash_balance'])}.**",
        f"- From the balance of {_inr(c['anchor_balance']['balance'])} on {c['anchor_balance']['as_of']}, plus {c['transactions_since_anchor']} later transactions (net {_inr(c['net_movement_since_anchor'])}).",
    ]
    for r in c["reconciliation"]:
        lines.append(f"- Statement balance on {r['as_of']}: {_inr(r['stated_balance'])} — " + ("matches the ledger." if r["reconciled"] else f"differs from the ledger by {_inr(r['difference'])}."))
    lines.append("\nThis is a bank balance, not profit: it includes loans, asset purchases, taxes and owner drawings.")
    return "\n".join(lines)


def _owed(q: str, call: ToolCaller, as_of) -> str:
    ok, o = call("get_receivables_and_payables", {})
    if o.get("status") != "ok":
        return o["message"]
    ok_u, up = call("get_upcoming_payments", {"days": 30})
    r, p = o["receivables"], o["payables"]
    lines = [
        f"**Customers owe you {_inr(r['outstanding'])}** — {_inr(r['overdue'])} of it overdue.",
    ]
    for i in r["overdue_items"][:6]:
        lines.append(f"- {i['item_id']} from {i['counterparty']}: {_inr(i['amount'])}, due {i['due_date']} ({i['days_overdue']} days late)")
    lines.append(f"\n**You owe suppliers {_inr(p['outstanding'])}** — {_inr(p['overdue'])} overdue.")
    for i in p["overdue_items"][:4]:
        lines.append(f"- {i['item_id']} to {i['counterparty']}: {_inr(i['amount'])}, due {i['due_date']} ({i['days_overdue']} days late)")
    if ok_u and up.get("status") == "ok":
        lines.append(f"\nBills due in the next 30 days: {_inr(up['upcoming_total'])}.")
        for i in up["upcoming"][:6]:
            lines.append(f"- {i['due_date']}: {i['description']} — {i['counterparty']}, {_inr(i['amount'])}")
    return "\n".join(lines)


def _summary(q: str, call: ToolCaller, as_of: pd.Timestamp) -> str:
    args: dict = {}
    m = re.search(r"last\s+(\d+)\s+months?", q, re.I)
    if m:
        args["start_date"] = str((as_of - pd.DateOffset(months=int(m.group(1))) + pd.Timedelta(days=1)).date())
    elif re.search(r"last month", q, re.I):
        end = as_of.replace(day=1) - pd.Timedelta(days=1)
        args = {"start_date": str(end.replace(day=1).date()), "end_date": str(end.date())}
    elif re.search(r"this month", q, re.I):
        args["start_date"] = str(as_of.replace(day=1).date())
    ok, s = call("get_financial_summary", args)
    if s.get("status") != "ok":
        return s["message"]
    o = s["other_flows"]
    lines = [
        f"**{s['period']['start']} to {s['period']['end']}**",
        f"- Revenue (cash received from sales): {_inr(s['revenue'])}",
        f"- Recorded operating expenses: {_inr(s['operating_expenses'])}",
        f"- **Estimated operating profit: {_inr(s['estimated_operating_profit'])}**"
        + (f" ({s['estimated_margin_pct']:.1f}% of revenue)" if s["estimated_margin_pct"] is not None else "")
        + " — an estimate before depreciation, unpaid bills and the interest in loan EMIs.",
        f"- Net cash movement (all money in − out): {_inr(s['net_cash_movement'])}",
        f"\nOutside operating profit: asset purchases {_inr(o['capex'])}, loan received {_inr(o['financing_in'])}, loan repayments {_inr(o['loan_repayments'])}, owner drawings {_inr(o['owner_drawings'])}, GST/TDS paid {_inr(o['tax_remitted'])}.",
    ]
    return "\n".join(lines)


def _records(q: str, call: ToolCaller, as_of) -> str:
    ids = IDS.findall(q)
    ok, r = call("get_supporting_records", {"record_ids": ids})
    if not ok:
        return r["message"]
    lines = []
    for t in r["transactions"]:
        lines.append(f"- {t['txn_id']}: {t['date']} · {t['description']} · {t['counterparty']} · {t['category']} · {'in' if t['direction'] == 'in' else 'out'} {_inr(t['amount'])}")
    for b in r["invoices_and_bills"]:
        lines.append(f"- {b['item_id']}: {b['kind']} · {b['counterparty']} · {_inr(b['amount'])} · due {b['due_date']} · {b['status']}")
    if r["not_found"]:
        lines.append(f"- Not found: {', '.join(r['not_found'])}")
    return "\n".join(lines) or "No matching records."


def _action(q: str, call: ToolCaller, as_of) -> str:
    ok, r = call("propose_action", {"action": q.strip()[:120], "reason": "Requested by the user in Ask FinPilot"})
    if not ok:
        return r["message"]
    if r.get("status") != "awaiting_human_approval":
        return r["message"]
    return f"**Added to the approval queue (#{r['approval_id']}).** {r['message']}"


INTENTS: list[tuple[re.Pattern, Callable]] = [
    (re.compile(r"\b(T\d{4}|U\d{5}|INV-\d{3,}|BILL-[A-Z0-9-]+|SCH-\d{3,})\b"), _records),
    (re.compile(r"\b(send|remind|reminder|pay (?:the|this|bill)|file|submit|transfer)\b", re.I), _action),
    (re.compile(r"\b(afford|buy|purchase|invest in|should (?:i|we) get)\b", re.I), _purchase),
    (re.compile(r"\b(forecast|next \d+ days|runway|run out|projection|cash flow|will (?:i|we) have)\b", re.I), _forecast),
    (re.compile(r"\b(duplicate|unusual|anomal|suspicious|odd|strange|fraud)\w*", re.I), _unusual),
    (re.compile(r"\b(expense|expenses|cost|costs|spend|spending|spent)\b", re.I), _expenses),
    (re.compile(r"\b(overdue|owe|owes|owed|receivable|payable|collect|pending|due|bills|upcoming)\b", re.I), _owed),
    (re.compile(r"\b(cash|balance|bank)\b", re.I), _cash),
    (re.compile(r"\b(profit\w*|revenue|sales|summary|margin|income|how (?:is|are|was) (?:the )?business|performance)\b", re.I), _summary),
]

HELP = (
    "I can answer questions like:\n"
    "- *How profitable were we in the last 6 months?*\n"
    "- *Why did expenses go up last month?*\n"
    "- *Any duplicate or unusual payments?*\n"
    "- *How much cash do we have, and who owes us?*\n"
    "- *Forecast our cash for the next 90 days.*\n"
    "- *Can we afford a ₹12 lakh packing machine on a loan at 11% for 3 years? It would save ₹45,000 a month.*"
)


def answer(question: str, call: ToolCaller, as_of: pd.Timestamp) -> str:
    for pattern, handler in INTENTS:
        if pattern.search(question):
            return handler(question, call, as_of)
    return HELP
