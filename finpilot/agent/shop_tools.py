"""
More approved tools for the agent: the shop's khata (customers and suppliers), health score, the
week's story, budgets and goals, GST and tax dates, what-if simulators — and *draft* actions.

Draft tools never change anything. They validate the request (an entry is dry-run through the same
khata code that saves it), and return a card the owner sees with Confirm / Cancel. Only the owner's
tap on Confirm — handled by the server, not the model — saves the entry, goal or budget, or opens
WhatsApp with the reminder text.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pandas as pd

from finpilot.agent.tools import Tool, ToolArgumentError, ToolContext, _date, _num, _obj, _reject_unknown, _str, _trim_evidence
from finpilot.data import books, khata
from finpilot.data.schema import Evidence, classify
from finpilot.engine import calendar_gst as cg
from finpilot.engine import whatif
from finpilot.engine.budget import budget_status, goal_plan, suggest_budgets
from finpilot.engine.common import fmt_inr, last_full_month, money
from finpilot.engine.health import health_score
from finpilot.engine.story import weekly_story

NEEDS_CONFIRMATION = "needs_confirmation"
CONFIRM_NOTE = ("Shown to the owner as a card with Confirm and Cancel buttons. Nothing has been saved or sent yet — "
                "tell the owner to check the card and tap Confirm if it is right.")


def _book(ctx: ToolContext) -> str:
    return getattr(ctx, "book", None) or "demo"


def _settings(ctx: ToolContext) -> dict:
    return books.settings(ctx.db_path, _book(ctx)) if ctx.db_path else dict(books.DEFAULT_SETTINGS)


def _obligations(ctx: ToolContext) -> pd.DataFrame | None:
    o = ctx.obligations
    if o is None or not len(o):
        return None
    o = o.copy()
    for c in ("issue_date", "due_date", "paid_date"):
        o[c] = pd.to_datetime(o[c])
    return o


def _ledger(ctx: ToolContext) -> pd.DataFrame:
    led = ctx.ledger.copy()
    led["date"] = pd.to_datetime(led["date"])
    return led


def _match_name(ctx: ToolContext, name: str) -> tuple[str | None, list[str]]:
    """Exact (case-insensitive) match, else a unique partial match. Returns (name, candidates)."""
    names = set(ctx.ledger["counterparty"].dropna().astype(str))
    o = ctx.obligations
    if o is not None and len(o):
        names |= set(o["counterparty"].dropna().astype(str))
    names.discard("")
    low = name.strip().lower()
    exact = [n for n in names if n.lower() == low]
    if exact:
        return exact[0], exact
    part = sorted(n for n in names if low in n.lower() or n.lower() in low)
    if len(part) == 1:
        return part[0], part
    words = [w for w in low.split() if len(w) > 2]
    loose = sorted(n for n in names if words and all(w in n.lower() for w in words))
    if len(loose) == 1:
        return loose[0], loose
    return None, (part or loose)[:8]


def _reliability(paid: pd.DataFrame) -> dict:
    p = paid.dropna(subset=["paid_date", "due_date"])
    if len(p) < 2:
        return {"on_time_pct": None, "avg_days_late": None, "paid_bills_counted": int(len(p)), "label": "too few paid bills to judge"}
    late = (p["paid_date"] - p["due_date"]).dt.days.clip(lower=0)
    on_time = round(float((late == 0).mean()) * 100)
    label = "pays on time" if on_time >= 80 else "sometimes late" if on_time >= 50 else "often late"
    return {"on_time_pct": on_time, "avg_days_late": round(float(late.mean()), 1), "paid_bills_counted": int(len(p)), "label": label}


# ---------------------------------------------------------------- read tools


def t_people(ctx: ToolContext, a: dict) -> dict:
    _reject_unknown(a, {"side", "sort_by", "months", "limit"})
    side = _str(a, "side", choices=("customers", "suppliers")) or "customers"
    sort_by = _str(a, "sort_by", choices=("overdue", "outstanding", "paid", "late")) or "overdue"
    months = _num(a, "months", 1, 24, default=12, integer=True)
    limit = _num(a, "limit", 1, 30, default=10, integer=True)
    kind, direction = ("receivable", "in") if side == "customers" else ("payable", "out")
    led = _ledger(ctx)
    start = ctx.as_of - pd.DateOffset(months=months) + pd.Timedelta(days=1)
    window = led[(led["date"] >= start) & (led["date"] <= ctx.as_of) & (led["direction"] == direction)]
    if side == "customers":
        window = window[[classify(c, "in") == "revenue" for c in window["category"]]]
    else:
        window = window[[classify(c, "out") in ("operating", "unclassified_out", "capex") for c in window["category"]]]
    paid_by = window.groupby("counterparty")["amount"].sum()
    last_by = window.groupby("counterparty")["date"].max()
    o = _obligations(ctx)
    o = o[o["kind"] == kind] if o is not None else None
    phones = books.contacts(ctx.db_path, _book(ctx)) if ctx.db_path else {}
    promises = {p["party"]: p for p in books.promises(ctx.db_path, _book(ctx))} if ctx.db_path else {}
    names = set(paid_by.index) | (set(o["counterparty"]) if o is not None else set())
    rows = []
    for n in names:
        g = o[o["counterparty"] == n] if o is not None else None
        pend = g[g["status"] == "pending"] if g is not None else pd.DataFrame(columns=["amount", "due_date"])
        od = pend[pend["due_date"] < ctx.as_of] if len(pend) else pend
        rel = _reliability(g[g["status"] == "paid"]) if g is not None else _reliability(pd.DataFrame(columns=["paid_date", "due_date"]))
        pr = promises.get(n)
        rows.append({
            "name": n,
            "paid_in_period" if side == "customers" else "paid_to_them_in_period": money(paid_by.get(n, 0.0)),
            "last_payment_date": str(last_by[n].date()) if n in last_by.index else None,
            "outstanding": money(pend["amount"].sum()) if len(pend) else 0.0,
            "overdue": money(od["amount"].sum()) if len(od) else 0.0,
            "overdue_items": [{"id": r.item_id, "amount": money(r.amount), "due_date": str(r.due_date.date()), "days_late": int((ctx.as_of - r.due_date).days)}
                              for r in od.sort_values("due_date").itertuples()][:6] if len(od) else [],
            "oldest_days_late": int((ctx.as_of - od["due_date"].min()).days) if len(od) else 0,
            **{f"reliability_{k}": v for k, v in rel.items()},
            "phone_saved": bool(phones.get(n)),
            "promise": {"amount": pr["amount"], "date": pr["date"], "broken": pd.Timestamp(pr["date"]) < ctx.as_of and len(pend) > 0} if pr else None,
        })
    paid_key = "paid_in_period" if side == "customers" else "paid_to_them_in_period"
    key = {"overdue": lambda r: (-r["overdue"], -r["outstanding"]), "outstanding": lambda r: (-r["outstanding"], -r["overdue"]),
           "paid": lambda r: (-r[paid_key],), "late": lambda r: (-(r["reliability_avg_days_late"] or -1), -r["overdue"])}[sort_by]
    rows.sort(key=lambda r: key(r) + (r["name"],))
    total_out = money(sum(r["outstanding"] for r in rows))
    return {
        "status": "ok",
        "side": side,
        "period": {"start": str(start.date()), "end": str(ctx.as_of.date())},
        "sorted_by": sort_by,
        "people_count": len(rows),
        "total_outstanding": total_out,
        "total_overdue": money(sum(r["overdue"] for r in rows)),
        f"total_{paid_key}": money(sum(r[paid_key] for r in rows)),
        "people": rows[:limit],
        "evidence": _trim_evidence(Evidence(
            method=f"Payments: {'sales received' if side == 'customers' else 'costs paid'} per party in the bank ledger over the period. "
                   "Outstanding/overdue: pending invoices or bills (overdue = past due date). Reliability: share of paid bills settled by the due date.",
            assumptions=("Party names are matched exactly as written in the records.",),
            limitations=("Cash sales recorded without a name are grouped under one name such as 'Walk-in customer'.",),
            record_ids=tuple(window["txn_id"]) + (tuple(o.loc[o["status"] == "pending", "item_id"]) if o is not None else ()),
            period=(str(start.date()), str(ctx.as_of.date())),
        ).to_dict()),
    }


def t_person(ctx: ToolContext, a: dict) -> dict:
    _reject_unknown(a, {"name"})
    name, cands = _match_name(ctx, _str(a, "name", 80, required=True))
    if name is None:
        return {"status": "not_found", "message": "No single customer or supplier matches that name.", "did_you_mean": cands}
    led = _ledger(ctx)
    mine = led[led["counterparty"] == name].sort_values("date")
    o = _obligations(ctx)
    g = o[o["counterparty"] == name] if o is not None else None
    pend = g[g["status"] == "pending"] if g is not None and len(g) else None
    phones = books.contacts(ctx.db_path, _book(ctx)) if ctx.db_path else {}
    pr = next((p for p in books.promises(ctx.db_path, _book(ctx)) if p["party"] == name), None) if ctx.db_path else None
    kind = "supplier" if g is not None and len(g) and (g["kind"] == "payable").all() else "customer" if g is not None and len(g) else (
        "customer" if (mine["direction"] == "in").sum() >= (mine["direction"] == "out").sum() else "supplier")
    return {
        "status": "ok",
        "name": name,
        "type": kind,
        "money_received_from_them": money(mine.loc[mine["direction"] == "in", "amount"].sum()),
        "money_paid_to_them": money(mine.loc[mine["direction"] == "out", "amount"].sum()),
        "transactions": int(len(mine)),
        "first_date": str(mine["date"].min().date()) if len(mine) else None,
        "last_date": str(mine["date"].max().date()) if len(mine) else None,
        "recent_transactions": [{"id": r.txn_id, "date": str(r.date.date()), "direction": r.direction, "amount": money(r.amount), "description": r.description}
                                for r in mine.tail(6).itertuples()][::-1],
        "outstanding": money(pend["amount"].sum()) if pend is not None else 0.0,
        "open_items": [{"id": r.item_id, "amount": money(r.amount), "due_date": str(r.due_date.date()),
                        "days_late": max(int((ctx.as_of - r.due_date).days), 0)} for r in pend.sort_values("due_date").itertuples()] if pend is not None else [],
        **{f"reliability_{k}": v for k, v in _reliability(g[g["status"] == "paid"] if g is not None else pd.DataFrame(columns=["paid_date", "due_date"])).items()},
        "phone_saved": bool(phones.get(name)),
        "promise": pr,
    }


def t_health(ctx: ToolContext, a: dict) -> dict:
    _reject_unknown(a, set())
    if not len(ctx.ledger):
        return {"status": "insufficient_data", "message": "No transactions yet."}
    h = health_score(ctx.ledger, ctx.balances, ctx.obligations, ctx.as_of)
    meaning = {"cash": "months of running costs in the bank", "profit": "estimated operating margin % (last 3 full months)",
               "collections": "% of money customers owe that is overdue", "bills": "% of supplier bills that are overdue",
               "momentum": "% change in sales, last 3 full months vs 3 before"}
    return {
        "status": "ok",
        "score": h["score"],
        "out_of": 100,
        "grade": h["grade"],
        "components": [{"key": c["key"], "measures": meaning[c["key"]], "value": c["value"], "points": c["points"], "max_points": c["max"], "status": c["status"]}
                       for c in h["components"]],
        "history": [{"month": x["month"], "score": x["score"]} for x in h.get("history", [])],
        "evidence": h["evidence"],
    }


def t_week(ctx: ToolContext, a: dict) -> dict:
    _reject_unknown(a, {"days"})
    days = _num(a, "days", 1, 31, default=7, integer=True)
    s = weekly_story(ctx.ledger, ctx.obligations, ctx.as_of, days)
    if s["status"] != "ok":
        return {"status": "insufficient_data", "message": "No transactions in this period."}
    ids = s.pop("record_ids")
    s["previous_period"] = s.pop("previous")
    s["this_period"] = s.pop("this")
    s["evidence"] = _trim_evidence(Evidence(
        method=f"Totals over the last {days} days up to the as-of date, compared with the {days} days before.",
        assumptions=("Sales are money received in sales categories; costs are running-cost categories.",),
        limitations=("A short window — one large payment can swing it.",),
        record_ids=tuple(ids), period=tuple(s["period"])).to_dict())
    return s


def t_budgets_goals(ctx: ToolContext, a: dict) -> dict:
    _reject_unknown(a, set())
    limits = books.budgets(ctx.db_path, _book(ctx)) if ctx.db_path else {}
    st = budget_status(ctx.ledger, limits, ctx.as_of) if limits else None
    goals = [goal_plan(g, ctx.as_of) for g in books.goals(ctx.db_path, _book(ctx))] if ctx.db_path else []
    return {
        "status": "ok",
        "budgets_set": bool(limits),
        "budget_month": st,
        "suggested_monthly_budgets": suggest_budgets(ctx.ledger, ctx.as_of) if len(ctx.ledger) else {},
        "goals": [{k: g.get(k) for k in ("id", "name", "target", "saved", "left", "pct", "target_date", "months_left", "per_month", "done")} for g in goals],
        "note": "Suggested budgets are the average monthly spend per category over the last 3 full months, rounded up to ₹500.",
    }


def t_tax(ctx: ToolContext, a: dict) -> dict:
    _reject_unknown(a, {"days"})
    days = _num(a, "days", 7, 92, default=45, integer=True)
    st = _settings(ctx)
    registered = st["gst_registered"] == "yes"
    end = ctx.as_of + pd.Timedelta(days=days)
    dates = []
    m = ctx.as_of.replace(day=1)
    while m <= end:
        for e in cg.statutory_dates(m.year, m.month, st["gst_filing"], registered):
            d = m.replace(day=e["day"])
            if ctx.as_of < d <= end:
                dates.append({"date": str(d.date()), "what": e["title"], "note": e.get("note", "")})
        m = (m + pd.offsets.MonthBegin(1)).normalize()
    out = {"status": "ok", "gst_registered": registered, "gst_filing": st["gst_filing"], "gst_rate_sales_pct": float(st["gst_rate_sales"]),
           "gst_rate_purchases_pct": float(st["gst_rate_purchases"]), "upcoming_due_dates": dates,
           "note": "Due dates are the usual statutory dates; check the GST portal for any extensions."}
    if registered and len(ctx.ledger):
        r_s, r_p = float(st["gst_rate_sales"]), float(st["gst_rate_purchases"])
        first = ctx.as_of.replace(day=1)
        cur = cg.gst_estimate(ctx.ledger, first, ctx.as_of, r_s, r_p)
        ps, pe = last_full_month(ctx.as_of)
        prev = cg.gst_estimate(ctx.ledger, ps, pe, r_s, r_p)
        cur["evidence"] = _trim_evidence(cur["evidence"])
        prev["evidence"] = _trim_evidence(prev["evidence"])
        out["gst_this_month_so_far"] = cur
        out["gst_last_full_month"] = prev
    return out


def t_whatif(ctx: ToolContext, a: dict) -> dict:
    _reject_unknown(a, {"kind", "price_change_pct", "volume_change_pct", "discount_pct", "sales_uplift_pct", "weeks", "monthly_salary", "extra_monthly_sales",
                        "start_after_months", "one_time_cost", "loan_amount", "interest_rate_pct", "years"})
    kind = _str(a, "kind", choices=("price", "discount", "hire", "loan"), required=True)
    if not len(ctx.ledger):
        return {"status": "insufficient_data", "message": "Needs a few months of transactions."}
    if kind == "price":
        r = whatif.price_change(ctx.ledger, ctx.as_of, _num(a, "price_change_pct", -50, 100, required=True), _num(a, "volume_change_pct", -90, 300, default=0))
    elif kind == "discount":
        r = whatif.discount(ctx.ledger, ctx.as_of, _num(a, "discount_pct", 0, 90, required=True), _num(a, "sales_uplift_pct", 0, 500, default=0),
                            _num(a, "weeks", 1, 52, default=4, integer=True))
    elif kind == "hire":
        r = whatif.hire(ctx.ledger, ctx.balances, ctx.obligations, ctx.as_of, _num(a, "monthly_salary", 1, 1e8, required=True),
                        _num(a, "extra_monthly_sales", 0, 1e9, default=0), _num(a, "start_after_months", 0, 24, default=1, integer=True),
                        _num(a, "one_time_cost", 0, 1e9, default=0))
    else:
        amount = _num(a, "loan_amount", 1, 1e10, required=True)
        rate, years = _num(a, "interest_rate_pct", 0, 40), _num(a, "years", 0.25, 30)
        if rate is None or years is None:
            return {"status": "needs_input", "message": "The interest rate and loan length must come from the lender's quote. FinPilot does not assume loan terms.",
                    "missing": [k for k, v in (("interest_rate_pct", rate), ("years", years)) if v is None]}
        r = whatif.loan(ctx.ledger, ctx.balances, ctx.obligations, ctx.as_of, amount, rate, years)
    r["kind"] = kind
    if "evidence" in r:
        r["evidence"] = _trim_evidence(r["evidence"])
    if isinstance(r.get("cash"), dict):
        r["cash"].pop("series", None)
    return r


# ---------------------------------------------------------------- draft actions (confirmed by the owner, never by the model)


def _draft(kind: str, title: str, summary: str, payload: dict, preview: dict | None = None) -> dict:
    return {"status": NEEDS_CONFIRMATION, "action_id": uuid.uuid4().hex[:10], "action": kind, "title": title, "summary": summary,
            "payload": payload, "preview": preview or {}, "message": CONFIRM_NOTE}


ENTRY_TITLES = {"sale": "Record a sale", "expense": "Record an expense", "credit_sale": "Give udhaar (sale on credit)",
                "payment_in": "Record money received", "bill": "Add a supplier bill", "payment_out": "Record a payment to a supplier"}


def t_draft_entry(ctx: ToolContext, a: dict) -> dict:
    _reject_unknown(a, {"kind", "amount", "party", "category", "mode", "note", "date", "due_date"})
    kind = _str(a, "kind", choices=khata.KINDS, required=True)
    amount = _num(a, "amount", 1, 1e10, required=True)
    date = _date(a, "date") or str(ctx.as_of.date())
    payload = {"kind": kind, "amount": amount, "date": date, "party": _str(a, "party", 80) or "", "category": _str(a, "category", 60) or "",
               "mode": _str(a, "mode", choices=khata.MODES) or "cash", "note": _str(a, "note", 200) or "", "due_date": _date(a, "due_date")}
    if payload["party"]:
        known, cands = _match_name(ctx, payload["party"])
        if known:
            payload["party"] = known
        elif kind in ("payment_in", "payment_out") and cands:
            return {"status": "ambiguous_name", "message": f"More than one name matches '{payload['party']}'.", "did_you_mean": cands}
    try:  # dry run through the real entry code: validates and tells us exactly what Confirm would do
        res = khata.record(khata.Tables(ctx.ledger, ctx.obligations, ctx.balances), kind, amount, date, party=payload["party"], category=payload["category"],
                           mode=payload["mode"], note=payload["note"], due_date=payload["due_date"], as_of=ctx.as_of)
    except khata.EntryError as e:
        return {"status": "invalid", "message": str(e)}
    preview = {"would_settle": [{"id": s["item_id"], "amount": s["amount"], "full": s["full"]} for s in res.settled]}
    if res.unapplied and kind in ("payment_in", "payment_out") and res.settled:
        preview["more_than_due"] = money(res.unapplied)
    return _draft("record_entry", ENTRY_TITLES[kind], res.summary, payload, preview)


def t_draft_reminder(ctx: ToolContext, a: dict) -> dict:
    _reject_unknown(a, {"customer"})
    from finpilot.api import khata_views  # local import: the api layer imports this package

    name, cands = _match_name(ctx, _str(a, "customer", 80, required=True))
    if name is None:
        return {"status": "not_found", "message": "No single customer matches that name.", "did_you_mean": cands}
    shim = SimpleNamespace(name=getattr(ctx, "business", "") or "our shop", obligations=ctx.obligations, ledger=ctx.ledger, as_of=ctx.as_of, book=_book(ctx))
    if ctx.db_path is None:
        return {"status": "not_available", "message": "Reminders need the app's saved books."}
    r = khata_views.reminders(shim, ctx.db_path, getattr(ctx, "lang", "en"), name)
    if not r:
        return {"status": "nothing_overdue", "customer": name, "message": f"Nothing from {name} is overdue, so there is nothing to remind them about."}
    r = r[0]
    first = name.split()[0].lower()
    notes = [m["text"] for m in books.memories(ctx.db_path, _book(ctx)) if first in m["text"].lower()]
    if notes:
        r["owner_notes"] = notes
    return _draft("send_reminder", f"WhatsApp reminder to {name}", f"Reminder for {fmt_inr(r['total'])} overdue",
                  {"customer": name, "text": r["text"], "whatsapp": r["whatsapp"], "phone_saved": bool(r["phone"])},
                  {"total": r["total"], "invoices": r["invoices"], "oldest_days_late": r["oldest_days_late"], "owner_notes": r.get("owner_notes", [])})


def t_draft_goal(ctx: ToolContext, a: dict) -> dict:
    _reject_unknown(a, {"name", "target", "target_date", "saved"})
    name = _str(a, "name", 60, required=True)
    target = _num(a, "target", 1, 1e10, required=True)
    saved = _num(a, "saved", 0, 1e10, default=0)
    when = _date(a, "target_date")
    if when and pd.Timestamp(when) <= ctx.as_of:
        raise ToolArgumentError("target_date must be in the future.")
    plan = goal_plan({"name": name, "target": target, "saved": saved, "target_date": when}, ctx.as_of)
    summary = f"Save {fmt_inr(target)} for {name}" + (f" by {pd.Timestamp(when):%d %b %Y}" if when else "")
    return _draft("create_goal", "Create a savings goal", summary, {"name": name, "target": target, "target_date": when, "saved": saved},
                  {"per_month": plan["per_month"], "months_left": plan["months_left"]})


def t_draft_budget(ctx: ToolContext, a: dict) -> dict:
    _reject_unknown(a, {"category", "monthly_limit"})
    cat = _str(a, "category", 60, required=True)
    limit = _num(a, "monthly_limit", 1, 1e10, required=True)
    known = {str(c) for c in ctx.ledger["category"].dropna().unique()}
    match = next((k for k in known if k.lower() == cat.lower()), None)
    if match is None:
        return {"status": "invalid", "message": f"No category called '{cat}'.", "categories": sorted(known)[:40]}
    st = budget_status(ctx.ledger, {match: limit}, ctx.as_of)["rows"][0]
    avg = suggest_budgets(ctx.ledger, ctx.as_of).get(match)
    return _draft("set_budget", "Set a monthly budget", f"{match}: {fmt_inr(limit)} a month", {"category": match, "monthly_limit": limit},
                  {"spent_this_month": st["spent"], "suggested_from_recent_average": avg})


# ---------------------------------------------------------------- the cash autopilot


def t_autopilot(ctx: ToolContext, a: dict) -> dict:
    _reject_unknown(a, set())
    from finpilot.engine import autopilot as ap

    st = _settings(ctx)
    try:
        safety = float(st.get("safety")) if st.get("safety") else None
    except ValueError:
        safety = None
    states = books.move_states(ctx.db_path, _book(ctx)) if ctx.db_path else {}
    approved = frozenset(k for k, v in states.items() if v in ("approved", "done"))
    p = ap.plan(ctx.ledger, ctx.balances, ctx.obligations, ctx.as_of, safety=safety, approved=approved)
    if p["status"] != "ok":
        return p
    return {
        "status": "ok", "today": p["today"], "safety_level": p["safety"], "horizon_days": p["horizon_days"],
        "if_nothing_is_done": p["baseline"], "with_the_agents_suggested_moves": p["with_suggested"],
        "with_moves_the_owner_approved": p["with_approved"] if approved else None,
        "main_causes_of_the_low_point": p["causes"], "invoices_not_counted_because_customer_is_late": p["at_risk"],
        "moves": [{"id": m["id"], "agent": m["agent"], "title": m["title"], "detail": m["detail"], "amount": m["amount"],
                   "raises_lowest_balance_by": m["impact"], "suggested": m["suggested"], "backup_only": m.get("backup", False),
                   **({"odds_with_plan_and_backup": m["odds_with_plan"], "interest_if_fully_used": m["interest_if_used"]} if m.get("backup") else {}),
                   "owner_decision": states.get(m["id"], "none")} for m in p["moves"]],
        "spendable_today_without_going_below_safety": p["baseline"]["spendable_today"],
        "odds_of_staying_above_safety": {"if_nothing_is_done": p["odds"]["baseline"]["p_safe"], "with_suggested_moves": p["odds"]["suggested"]["p_safe"],
                                         "with_approved_moves": p["odds"]["approved"]["p_safe"] if p["odds"]["approved"] else None},
        "odds_of_running_out": {"if_nothing_is_done": p["odds"]["baseline"]["p_short"], "with_suggested_moves": p["odds"]["suggested"]["p_short"]},
        "bad_case_lowest_balance_1_in_10": p["odds"]["baseline"]["bad_case_lowest"],
        "simulation": {"futures": p["odds"]["baseline"]["sims"], "combinations_scored": p["search"]["combinations"], "plans_stress_tested": p["search"]["stress_tested"],
                       "assumptions": p["odds"]["assumptions"]},
        "audit_rerun_matches_plan": p["audit"]["matches"],
        "evidence": _trim_evidence(p["evidence"]),
    }


def t_plan_purchase(ctx: ToolContext, a: dict) -> dict:
    _reject_unknown(a, {"amount", "date", "label"})
    from finpilot.engine import autopilot as ap

    amount = a.get("amount")
    if not isinstance(amount, (int, float)) or isinstance(amount, bool) or amount <= 0:
        raise ToolArgumentError("'amount' must be a positive number of rupees.")
    when = _str(a, "date", 10)
    if when:
        try:
            when_ts = pd.Timestamp(when)
        except ValueError as e:
            raise ToolArgumentError("'date' must be YYYY-MM-DD.") from e
        if when_ts <= pd.Timestamp(ctx.as_of):
            raise ToolArgumentError("'date' must be after the as-of date.")
    label = _str(a, "label", 60) or "Purchase"
    st = _settings(ctx)
    try:
        safety = float(st.get("safety")) if st.get("safety") else None
    except ValueError:
        safety = None
    states = books.move_states(ctx.db_path, _book(ctx)) if ctx.db_path else {}
    approved = frozenset(k for k, v in states.items() if v in ("approved", "done"))
    r = ap.afford(ctx.ledger, ctx.balances, ctx.obligations, ctx.as_of, float(amount), when or None, label, safety=safety, approved=approved)
    if r.get("status") != "ok":
        return r
    return {"status": "ok", "verdict": r["verdict"],
            "verdict_meaning": {"yes": "safe without any moves", "yes_if": "safe if the listed moves are approved", "risky": "possible but the odds of staying above safety are low",
                                "not_now": "would push cash below safety even with every move"}[r["verdict"]],
            "amount": r["amount"], "date": r["date"], "label": r["label"], "safety_level": r["safety"],
            "without_moves": r["without_moves"], "with_agents_moves": r["with_plan"], "earliest_safe_date_without_moves": r["earliest_safe_date_without_moves"],
            "evidence": _trim_evidence(r["evidence"])}


# ---------------------------------------------------------------- plan, memory, review queue


PLAN_STATES = ("todo", "doing", "done", "skipped")


def t_update_plan(ctx: ToolContext, a: dict) -> dict:
    _reject_unknown(a, {"steps"})
    steps = a.get("steps")
    if not isinstance(steps, list) or not 1 <= len(steps) <= 8:
        raise ToolArgumentError("'steps' must be a list of 1 to 8 steps.")
    out = []
    for st in steps:
        if not isinstance(st, dict):
            raise ToolArgumentError("Each step must be an object with 'title' and 'status'.")
        title = _str(st, "title", 90, required=True)
        status = _str(st, "status", choices=PLAN_STATES) or "todo"
        out.append({"title": title, "status": status})
    return {"status": "ok", "plan": out, "message": "Plan shown to the owner. Update it as you finish each step."}


def t_remember(ctx: ToolContext, a: dict) -> dict:
    _reject_unknown(a, {"fact"})
    fact = _str(a, "fact", 300, required=True)
    if ctx.db_path is None:
        return {"status": "not_available", "message": "Memory needs the app's saved books."}
    mid = books.add_memory(ctx.db_path, _book(ctx), fact)
    return {"status": "remembered", "id": mid, "fact": fact, "message": "Saved to the agent's memory for this shop. The owner can see and delete it."}


def t_forget(ctx: ToolContext, a: dict) -> dict:
    _reject_unknown(a, {"id"})
    mid = _num(a, "id", 1, 1e9, required=True, integer=True)
    if ctx.db_path is None or not books.delete_memory(ctx.db_path, _book(ctx), mid):
        return {"status": "not_found", "message": f"No memory #{mid}."}
    return {"status": "forgotten", "id": mid}


def t_recall(ctx: ToolContext, a: dict) -> dict:
    _reject_unknown(a, set())
    mem = books.memories(ctx.db_path, _book(ctx)) if ctx.db_path else []
    return {"status": "ok", "memories": [{"id": m["id"], "fact": m["text"]} for m in mem]}


def _review_rows(ctx: ToolContext) -> pd.DataFrame:
    led = ctx.ledger
    mask = led["category"].isin(["Uncategorised", "Unknown", ""]) | led["reference"].astype(str).str.contains("auto:guess", na=False)
    return led[mask]


def t_review_queue(ctx: ToolContext, a: dict) -> dict:
    _reject_unknown(a, set())
    rows = _review_rows(ctx)
    groups = []
    for (party, direction), g in rows.groupby(["counterparty", "direction"]):
        groups.append({"party": party, "direction": direction, "count": int(len(g)), "total": money(g["amount"].sum()),
                       "current_category": g["category"].iloc[0], "is_guess": bool(g["reference"].astype(str).str.contains("auto:guess").any()),
                       "example": str(g["description"].iloc[0])[:80]})
    groups.sort(key=lambda r: -r["total"])
    return {"status": "ok", "lines_to_review": int(len(rows)), "groups": groups[:15]}


# ---------------------------------------------------------------- more drafts


def t_draft_promise(ctx: ToolContext, a: dict) -> dict:
    _reject_unknown(a, {"customer", "amount", "date", "note"})
    name, cands = _match_name(ctx, _str(a, "customer", 80, required=True))
    if name is None:
        return {"status": "not_found", "message": "No single customer matches that name.", "did_you_mean": cands}
    when = _date(a, "date", required=True)
    if pd.Timestamp(when) < ctx.as_of:
        raise ToolArgumentError("The promised date can't be in the past.")
    amount = _num(a, "amount", 0, 1e10, default=0)
    note = _str(a, "note", 200) or ""
    summary = f"{name} promised {fmt_inr(amount) + ' ' if amount else ''}by {pd.Timestamp(when):%d %b %Y}"
    return _draft("record_promise", "Note a promise to pay", summary, {"customer": name, "amount": amount, "date": when, "note": note})


def t_draft_recategorise(ctx: ToolContext, a: dict) -> dict:
    _reject_unknown(a, {"party", "category", "remember_for_party"})
    name, cands = _match_name(ctx, _str(a, "party", 80, required=True))
    if name is None:
        return {"status": "not_found", "message": "No single party matches that name.", "did_you_mean": cands}
    cat = _str(a, "category", 60, required=True)
    known = {str(c) for c in ctx.ledger["category"].dropna().unique()} | {"Uncategorised"}
    from finpilot.data.schema import CATEGORY_CLASS

    known |= {c.title() for c in CATEGORY_CLASS}
    match = next((k for k in known if k.lower() == cat.lower()), None)
    if match is None:
        return {"status": "invalid", "message": f"No category called '{cat}'.", "categories": sorted(known)[:40]}
    rows = _review_rows(ctx)
    rows = rows[rows["counterparty"] == name]
    if not len(rows):
        return {"status": "nothing_to_change", "message": f"No unreviewed lines for {name}."}
    remember = bool(a.get("remember_for_party", True))
    ids = rows["txn_id"].tolist()
    return _draft("recategorise", "Fix categories", f"{len(ids)} payment(s) from/to {name} → {match}",
                  {"ids": ids[:200], "category": match, "party": name, "remember": remember},
                  {"count": len(ids), "total": money(rows["amount"].sum()), "from": sorted(set(rows["category"]))})


PLAN_TOOLS: list[Tool] = [
    Tool("update_plan",
         "Show the owner your step-by-step plan as a live checklist, and update it as you go. Call it first for anything with more than one step "
         "(a mission like 'collect my money', a check-up), then again with statuses changed (todo, doing, done, skipped).",
         _obj({"steps": {"type": "array", "maxItems": 8, "items": {"type": "object", "properties": {"title": {"type": "string"}, "status": {"type": "string", "enum": list(PLAN_STATES)}},
                                                                    "required": ["title", "status"]}}}, ["steps"]),
         t_update_plan),
    Tool("remember", "Save a lasting fact or preference the owner tells you about their shop (e.g. 'Ramesh is my brother — never send him reminders', 'GST is filed by my CA Mr. Shah'). "
         "Not for figures — those always come from the records. The owner can see and delete memories.",
         _obj({"fact": {"type": "string"}}, ["fact"]), t_remember),
    Tool("forget", "Delete one saved memory by its id.", _obj({"id": {"type": "integer"}}, ["id"]), t_forget),
    Tool("recall_memory", "List the facts and preferences the owner asked you to remember.", _obj({}), t_recall),
    Tool("get_cash_autopilot",
         "The cash autopilot: today's cash, the owner's safety level, the lowest balance in the next 90 days if nothing is done (and the date cash falls "
         "below safety or runs out), its main causes, invoices not counted because the customer is already late, and the agents' moves "
         "(collect, move a supplier bill, pause spending, set aside GST) each with how much it raises the lowest balance, and the owner's decisions.",
         _obj({}), t_autopilot),
    Tool("plan_purchase",
         "Can the business pay for something (a machine, a deposit, a big order) on a date and stay above its safety level? Re-runs the cash autopilot with the "
         "payment included: verdict (yes / yes_if moves approved / risky / not_now), the lowest balance and the odds of staying safe without and with the agents' "
         "moves, and the earliest date it could be paid without any moves. Prefer this over simulate_purchase for cash purchases.",
         _obj({"amount": {"type": "number", "minimum": 1}, "date": {"type": "string", "description": "YYYY-MM-DD, default tomorrow"}, "label": {"type": "string"}}, ["amount"]),
         t_plan_purchase),
    Tool("get_review_queue", "Bank lines that need a category (uncategorised, or incoming money only guessed as sales), grouped by party, with the current guess.",
         _obj({}), t_review_queue),
    Tool("draft_promise", "Prepare a note that a customer promised to pay (by a date, optionally an amount) for the owner to confirm. FinPilot then flags it if the date passes unpaid.",
         _obj({"customer": {"type": "string"}, "amount": {"type": "number", "minimum": 0}, "date": {"type": "string", "description": "YYYY-MM-DD"}, "note": {"type": "string"}}, ["customer", "date"]),
         t_draft_promise),
    Tool("draft_recategorise", "Prepare a fix for the category of a party's unreviewed bank lines (and remember it for future lines) for the owner to confirm.",
         _obj({"party": {"type": "string"}, "category": {"type": "string"}, "remember_for_party": {"type": "boolean"}}, ["party", "category"]),
         t_draft_recategorise),
]


S = {"type": "string"}
SHOP_TOOLS: list[Tool] = [
    Tool("get_customers_and_suppliers",
         "The khata: customers (or suppliers) with how much they paid in the period, what they still owe (outstanding/overdue with days late), "
         "how reliably they pay, last payment, saved phone and any payment promise. Sort by overdue, outstanding, paid (best customers) or late (slowest payers).",
         _obj({"side": {"type": "string", "enum": ["customers", "suppliers"]}, "sort_by": {"type": "string", "enum": ["overdue", "outstanding", "paid", "late"]},
               "months": {"type": "integer", "minimum": 1, "maximum": 24}, "limit": {"type": "integer", "minimum": 1, "maximum": 30}}),
         t_people),
    Tool("get_person_details", "Everything about one customer or supplier by name: money in and out, recent transactions, open invoices/bills, payment reliability, promise.",
         _obj({"name": S}, ["name"]), t_person),
    Tool("get_health_score", "The business health score out of 100 from five checks (cash cushion, margin, collections, bills, sales momentum), with each check's value and points and the score in recent months.",
         _obj({}), t_health),
    Tool("get_weekly_story", "What happened in the last N days (default 7) vs the N days before: sales, costs, money in/out, best day, top customer, biggest expense, udhaar given and collected.",
         _obj({"days": {"type": "integer", "minimum": 1, "maximum": 31}}), t_week),
    Tool("get_budgets_and_goals", "Monthly budgets the owner set with spending so far and month-end pace, suggested budgets from recent averages, and savings goals with the monthly saving needed.",
         _obj({}), t_budgets_goals),
    Tool("get_tax_calendar_and_gst", "Upcoming GST/TDS due dates, the owner's GST settings, and an estimate of GST to set aside for this month so far and last full month (an estimate, not a return).",
         _obj({"days": {"type": "integer", "minimum": 7, "maximum": 92}}), t_tax),
    Tool("run_what_if",
         "What-if simulators on the shop's own averages: kind=price (price_change_pct, optional volume_change_pct), discount (discount_pct, sales_uplift_pct, weeks), "
         "hire (monthly_salary, extra_monthly_sales, start_after_months, one_time_cost) or loan (loan_amount, interest_rate_pct, years — rate and years must come from the user).",
         _obj({"kind": {"type": "string", "enum": ["price", "discount", "hire", "loan"]}, "price_change_pct": {"type": "number"}, "volume_change_pct": {"type": "number"},
               "discount_pct": {"type": "number"}, "sales_uplift_pct": {"type": "number"}, "weeks": {"type": "integer"}, "monthly_salary": {"type": "number"},
               "extra_monthly_sales": {"type": "number"}, "start_after_months": {"type": "integer"}, "one_time_cost": {"type": "number"},
               "loan_amount": {"type": "number"}, "interest_rate_pct": {"type": "number"}, "years": {"type": "number"}}, ["kind"]),
         t_whatif),
    Tool("draft_entry",
         "Prepare a khata entry for the owner to confirm: sale, expense, credit_sale (udhaar given), payment_in (customer paid; settles their oldest dues), bill (supplier bill), "
         "payment_out (paid a supplier). It is checked but NOT saved — the owner sees a card and taps Confirm. Use when the owner asks to add/record something.",
         _obj({"kind": {"type": "string", "enum": list(khata.KINDS)}, "amount": {"type": "number", "minimum": 1}, "party": S, "category": S,
               "mode": {"type": "string", "enum": list(khata.MODES)}, "note": S, "date": {"type": "string", "description": "YYYY-MM-DD, default today"},
               "due_date": {"type": "string", "description": "YYYY-MM-DD, for udhaar or bills"}}, ["kind", "amount"]),
         t_draft_entry),
    Tool("draft_reminder", "Prepare a polite WhatsApp payment reminder to a customer with overdue dues. NOT sent — the owner reviews it and taps to open WhatsApp.",
         _obj({"customer": S}, ["customer"]), t_draft_reminder),
    Tool("draft_goal", "Prepare a savings goal (name, target ₹, optional target_date and amount already saved) for the owner to confirm. Shows the monthly saving needed.",
         _obj({"name": S, "target": {"type": "number", "minimum": 1}, "target_date": {"type": "string", "description": "YYYY-MM-DD"}, "saved": {"type": "number", "minimum": 0}}, ["name", "target"]),
         t_draft_goal),
    Tool("draft_budget", "Prepare a monthly spending limit for one cost category for the owner to confirm. Shows this month's spending so far.",
         _obj({"category": S, "monthly_limit": {"type": "number", "minimum": 1}}, ["category", "monthly_limit"]),
         t_draft_budget),
] + PLAN_TOOLS
