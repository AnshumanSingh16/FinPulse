"""
Owner-facing views. Each function turns tested engine results into plain-language payloads for the
web app: a headline, the numbers behind it, and the evidence. No new financial logic lives here —
only selection, grouping and wording — so every figure still traces back to finpilot.engine.
"""

from __future__ import annotations

from urllib.parse import quote

import pandas as pd

from finpilot.engine.cash import cash_position, obligations_status, upcoming_payments
from finpilot.engine.common import fmt_inr, last_full_month, money, prepare_ledger
from finpilot.engine.decision import SCENARIOS, Purchase, default_buffer, simulate_purchase
from finpilot.engine.expenses import compare_expenses, unusual_transactions
from finpilot.engine.forecast import ForecastOptions, forecast_cash_flow
from finpilot.engine.summary import financial_summary

from .dataset import Dataset

SCENARIO_NAMES = {"optimistic": "If things go well", "base": "Most likely", "downside": "If the next few months are tough"}


# ---------------------------------------------------------------- formatting


def short(x: float | None) -> str:
    """Compact Indian format for headlines: ₹14.85 L, ₹1.2 Cr, ₹45,000."""
    if x is None:
        return "—"
    a, sign = abs(x), "−" if x < 0 else ""
    if a >= 1e7:
        return f"{sign}₹{a / 1e7:.2f}".rstrip("0").rstrip(".") + " Cr"
    if a >= 1e5:
        return f"{sign}₹{a / 1e5:.2f}".rstrip("0").rstrip(".") + " L"
    return fmt_inr(x)


def day(d) -> str:
    return pd.Timestamp(d).strftime("%d %b").lstrip("0")


def day_full(d) -> str:
    return pd.Timestamp(d).strftime("%d %b %Y").lstrip("0")


def pct_change(new: float, old: float) -> float | None:
    """None when there's no meaningful % (no base, or a swing from profit to loss)."""
    if not old or (new < 0) != (old < 0):
        return None
    return round((new - old) / abs(old) * 100, 1)


def evidence(ev: dict, title: str, max_ids: int = 200) -> dict:
    ids = list(ev.get("record_ids") or [])
    return {
        "title": title,
        "method": ev.get("method", ""),
        "assumptions": list(ev.get("assumptions") or []),
        "limitations": list(ev.get("limitations") or []),
        "record_ids": ids[:max_ids],
        "record_count": len(ids),
    }


def _plain_item(label: str) -> str:
    """'SCH-0056 to Staff payroll' → 'Pay Staff payroll'; 'INV-0120 from Metro Foods' → 'From Metro Foods'."""
    if " to " in label:
        return "Pay " + label.split(" to ", 1)[1]
    if " from " in label:
        return "From " + label.split(" from ", 1)[1]
    return label


# ---------------------------------------------------------------- shared pieces


def _cash_and_outlook(ds: Dataset, days: int = 90):
    pos = cash_position(ds.ledger, ds.balances, ds.as_of)
    buffer = default_buffer(ds.ledger, ds.as_of)
    fc = None
    if pos["status"] == "ok":
        fc = forecast_cash_flow(ds.ledger, ds.balances, ds.obligations, ds.as_of, ForecastOptions(horizon_days=days, include_run_rate=True, min_buffer=buffer))
    return pos, buffer, fc


def _history(ds: Dataset, cash_now: float, days: int = 90) -> list[dict]:
    """Bank balance on each past day, worked back from today's balance: balance(d) = cash − Σ movements after d."""
    df = prepare_ledger(ds.ledger)
    df = df[df["date"] <= ds.as_of]
    start = ds.as_of - pd.Timedelta(days=days)
    daily = df[df["date"] > start].groupby("date")["signed"].sum()
    out = []
    after = 0.0
    for d in pd.date_range(start, ds.as_of, freq="D")[::-1]:
        out.append({"date": str(d.date()), "balance": money(cash_now - after)})
        after += float(daily.get(d, 0.0))
    return out[::-1]


def status(pos: dict, fc: dict | None, buffer: float) -> dict:
    if pos["status"] != "ok":
        return {
            "tone": "neutral",
            "headline": "Add your bank balance to see where you stand",
            "detail": "FinPilot needs one balance from your bank statement to work out your cash. It never guesses cash from sales.",
        }
    if fc and fc["status"] == "ok" and fc["first_negative_date"]:
        return {
            "tone": "bad",
            "headline": f"Cash could run out around {day(fc['first_negative_date'])}",
            "detail": "Based on bills due, money customers owe you and your usual monthly spending. Act now: chase payments or delay big purchases.",
        }
    if fc and fc["status"] == "ok" and fc["first_date_below_buffer"]:
        return {
            "tone": "caution",
            "headline": f"Cash could get tight around {day(fc['first_date_below_buffer'])}",
            "detail": f"Your balance may drop below {short(buffer)} — one month of running costs — with a low of {short(fc['lowest_balance'])} on {day(fc['lowest_balance_date'])}.",
        }
    months = pos["cash_balance"] / buffer if buffer else None
    detail = f"{short(pos['cash_balance'])} in the bank"
    if months:
        detail += f" — about {months:.1f} months of running costs"
    detail += ". On current plans it stays above one month's costs for the next 90 days."
    return {"tone": "good", "headline": "Your business is in good shape", "detail": detail}


def _month_periods(as_of: pd.Timestamp):
    this0, this1 = last_full_month(as_of)
    prev1 = this0 - pd.Timedelta(days=1)
    return (this0, this1), (prev1.replace(day=1), prev1)


def _summary_numbers(ds: Dataset, start, end) -> dict | None:
    s = financial_summary(ds.ledger, start, end)
    if s["status"] != "ok":
        return None
    return {
        "label": pd.Timestamp(start).strftime("%B %Y"),
        "sales": s["revenue"],
        "costs": s["operating_expenses"],
        "profit": s["estimated_operating_profit"],
        "margin_pct": s["estimated_margin_pct"],
        "evidence": evidence(s["evidence"], f"How we worked out {pd.Timestamp(start):%B}'s profit"),
    }


# ---------------------------------------------------------------- home


def attention(ds: Dataset, pos: dict, fc: dict | None, buffer: float) -> list[dict]:
    items: list[dict] = []
    if pos["status"] == "ok":  # (a missing balance is already the headline, so it isn't repeated here)
        for r in pos["reconciliation"]:
            if not r["reconciled"]:
                items.append({
                    "id": f"recon-{r['as_of']}", "tone": "bad", "icon": "alert",
                    "title": "Your records don't match the bank",
                    "body": f"On {day_full(r['as_of'])} the bank said {short(r['stated_balance'])}, your records say {short(r['computed_from_ledger'])}. Some transactions may be missing or entered twice.",
                    "action": {"type": "review", "label": "Check transactions", "ids": []},
                })
    if fc and fc["status"] == "ok" and (fc["first_negative_date"] or fc["first_date_below_buffer"]):
        neg = fc["first_negative_date"]
        items.append({
            "id": "cash-outlook", "tone": "bad" if neg else "caution", "icon": "trend",
            "title": f"Cash may {'run out' if neg else 'get tight'} on {day(neg or fc['first_date_below_buffer'])}",
            "body": f"Lowest expected balance: {short(fc['lowest_balance'])} on {day(fc['lowest_balance_date'])}. See what's coming in and out.",
            "action": {"type": "open", "label": "See cash ahead", "href": "/plan/"},
        })

    obl = obligations_status(ds.obligations, ds.as_of)
    if obl["status"] == "ok":
        by_customer: dict[str, list[dict]] = {}
        for i in obl["receivables"]["overdue_items"]:
            by_customer.setdefault(i["counterparty"], []).append(i)
        ranked = sorted(by_customer.items(), key=lambda kv: -sum(i["amount"] for i in kv[1]))
        for name, inv in ranked[:3]:
            total = money(sum(i["amount"] for i in inv))
            oldest = max(i["days_overdue"] for i in inv)
            items.append({
                "id": f"owed-{name}", "tone": "bad" if oldest > 30 else "caution", "icon": "customer",
                "title": f"{name} owes you {short(total)}",
                "body": f"{len(inv)} invoice{'s' if len(inv) > 1 else ''} overdue, the oldest by {oldest} days.",
                "action": {"type": "remind", "label": "Draft a reminder", "customer": name},
            })
        for i in obl["payables"]["overdue_items"][:2]:
            items.append({
                "id": f"bill-{i['item_id']}", "tone": "caution", "icon": "bill",
                "title": f"Bill to {i['counterparty']} is {i['days_overdue']} days late",
                "body": f"{short(i['amount'])} was due on {day(i['due_date'])}. Late payments can cost supplier goodwill.",
                "action": {"type": "todo", "label": "Add to my to-dos", "text": f"Pay {i['counterparty']} {fmt_inr(i['amount'])} ({i['item_id']})"},
            })

    flags = unusual_transactions(ds.ledger, ds.as_of, lookback_days=90)["flags"]
    for f in [f for f in flags if f["type"] == "possible_duplicate"][:2]:
        items.append({
            "id": f"dup-{'-'.join(f['txn_ids'])}", "tone": "caution", "icon": "copy",
            "title": f"Possible double payment to {f['counterparty']}",
            "body": f"{len(f['txn_ids'])} identical payments of {short(f['amount'])} on {day(f['date'])}. Worth checking with your bank or supplier.",
            "action": {"type": "review", "label": "Review payments", "ids": f["txn_ids"]},
        })
    unusual = sorted([f for f in flags if f["type"] != "possible_duplicate"], key=lambda f: -(f.get("excess") or f["amount"]))
    for f in unusual[:2]:
        items.append({
            "id": f"odd-{'-'.join(f['txn_ids'])}", "tone": "info", "icon": "spark",
            "title": f"Unusual {f['category'].lower()} payment: {short(f['amount'])}",
            "body": f"Paid to {f['counterparty']} on {day(f['date'])}. {f['reason']}",
            "action": {"type": "review", "label": "See payment", "ids": f["txn_ids"]},
        })
    return items


def home(ds: Dataset) -> dict:
    pos, buffer, fc = _cash_and_outlook(ds)
    cash = {"known": pos["status"] == "ok"}
    if cash["known"]:
        c = pos["cash_balance"]
        cash.update({
            "amount": c,
            "label": short(c),
            "exact": fmt_inr(c),
            "months_of_costs": round(c / buffer, 1) if buffer else None,
            "cushion": buffer,
            "cushion_label": short(buffer),
            "reconciled": bool(pos["reconciliation"]) and all(r["reconciled"] for r in pos["reconciliation"]),
            "history": _history(ds, c),
            "outlook": [{"date": d["date"], "balance": d["balance"]} for d in fc["daily"]] if fc and fc["status"] == "ok" else [],
            "in_90_days": fc["checkpoints"][min(2, len(fc["checkpoints"]) - 1)]["balance"] if fc and fc["status"] == "ok" else None,
            "evidence": evidence(pos["evidence"], "How we know your cash"),
        })
    else:
        cash["message"] = pos["message"]

    (t0, t1), (p0, p1) = _month_periods(ds.as_of)
    this, prev = _summary_numbers(ds, t0, t1), _summary_numbers(ds, p0, p1)
    if this is None:  # no complete month yet (e.g. a fresh upload): show this month so far
        t0, t1 = ds.as_of.replace(day=1), ds.as_of
        p1 = t0 - pd.Timedelta(days=1)
        p0 = p1.replace(day=1)
        this, prev = _summary_numbers(ds, t0, t1), _summary_numbers(ds, p0, p1)
        if this:
            this["label"] = f"{t0:%B} so far"
    month = None
    if this:
        month = {**this, "previous": prev}
        if prev:
            month["change"] = {k: pct_change(this[k], prev[k]) for k in ("sales", "costs", "profit")}

    spending, insight = [], None
    cmp = compare_expenses(ds.ledger, (p0, p1), (t0, t1))
    if cmp["status"] == "ok":
        rows = sorted(cmp["by_category"], key=lambda r: -r["period_b"])
        spending = [{"category": r["category"], "amount": r["period_b"], "previous": r["period_a"], "change_pct": r["change_pct"]} for r in rows if r["period_b"] > 0][:6]
        tp = cmp["total_change_pct"]
        if tp is not None and abs(tp) >= 10:
            up = tp > 0
            mover = max(cmp["by_category"], key=lambda r: r["change"] if up else -r["change"])
            insight = {
                "tone": "caution" if up else "good",
                "text": f"Running costs {'rose' if up else 'fell'} {abs(tp):.0f}% compared with {pd.Timestamp(p0):%B}. "
                        f"Biggest {'jump' if up else 'drop'}: {mover['category'].lower()} ({'+' if mover['change'] > 0 else '−'}{short(abs(mover['change']))}).",
                "ask": f"Why did costs {'go up' if up else 'go down'} in {pd.Timestamp(t0):%B}?",
            }

    six = financial_summary(ds.ledger, (t0 - pd.DateOffset(months=5)).replace(day=1), t1)
    trend = [
        {"month": pd.Timestamp(m["month"] + "-01").strftime("%b"), "sales": m["revenue"], "costs": m["operating_expenses"], "profit": m["estimated_operating_profit"]}
        for m in six.get("monthly", [])
    ] if six["status"] == "ok" else []

    up = upcoming_payments(ds.obligations, ds.as_of, 14)
    upcoming = [
        {"date": i["due_date"], "day": day(i["due_date"]), "name": i["counterparty"], "what": i["description"], "amount": i["amount"]}
        for i in (up["upcoming"] if up["status"] == "ok" else [])
    ]
    return {
        "business": ds.name,
        "is_demo": ds.is_demo,
        "as_of": str(ds.as_of.date()),
        "as_of_label": day_full(ds.as_of),
        "status": status(pos, fc, buffer),
        "cash": cash,
        "month": month,
        "insight": insight,
        "attention": attention(ds, pos, fc, buffer),
        "spending": spending,
        "trend": trend,
        "upcoming": upcoming,
        "upcoming_total": up.get("upcoming_total") if up["status"] == "ok" else None,
    }


# ---------------------------------------------------------------- money


def transactions(ds: Dataset, q: str = "", direction: str = "", category: str = "", ids: list[str] | None = None, limit: int = 100, offset: int = 0) -> dict:
    df = ds.ledger.copy()
    df["date"] = pd.to_datetime(df["date"])
    if ids:
        df = df[df["txn_id"].isin(ids)]
    if direction in ("in", "out"):
        df = df[df["direction"] == direction]
    if category:
        df = df[df["category"] == category]
    if q:
        ql = q.lower()
        hay = (df["description"].astype(str) + " " + df["counterparty"].astype(str) + " " + df["category"].astype(str) + " " + df["txn_id"].astype(str)).str.lower()
        df = df[hay.str.contains(ql, regex=False)]
    df = df.sort_values(["date", "txn_id"], ascending=False)
    page = df.iloc[offset: offset + limit]
    return {
        "total": int(len(df)),
        "money_in": money(df.loc[df["direction"] == "in", "amount"].sum()),
        "money_out": money(df.loc[df["direction"] == "out", "amount"].sum()),
        "categories": sorted(ds.ledger["category"].dropna().unique().tolist()),
        "rows": [
            {"id": r.txn_id, "date": str(r.date.date()), "day": day_full(r.date), "description": r.description, "party": r.counterparty,
             "category": r.category, "direction": r.direction, "amount": float(r.amount), "mode": getattr(r, "payment_mode", None) or None}
            for r in page.itertuples()
        ],
    }


def owed(ds: Dataset) -> dict:
    o = ds.obligations
    st = obligations_status(o, ds.as_of)
    if st["status"] != "ok":
        return {"status": "missing", "message": "Upload your invoices and bills to see who owes you and what you owe."}
    o = o.copy()
    o["due_date"] = pd.to_datetime(o["due_date"])
    pend = o[o["status"] == "pending"]

    def groups(kind: str) -> list[dict]:
        out = {}
        for r in pend[pend["kind"] == kind].sort_values("due_date").itertuples():
            late = int((ds.as_of - r.due_date).days)
            g = out.setdefault(r.counterparty, {"name": r.counterparty, "total": 0.0, "overdue": 0.0, "items": []})
            g["total"] += float(r.amount)
            if late > 0:
                g["overdue"] += float(r.amount)
            g["items"].append({
                "id": r.item_id, "what": r.description, "amount": float(r.amount), "due": str(r.due_date.date()), "due_label": day_full(r.due_date),
                "state": "overdue" if late > 0 else ("due_soon" if late >= -7 else "upcoming"), "days_late": max(late, 0), "days_left": max(-late, 0),
            })
        res = [{**g, "total": money(g["total"]), "overdue": money(g["overdue"])} for g in out.values()]
        return sorted(res, key=lambda g: (-g["overdue"], -g["total"]))

    r, p = st["receivables"], st["payables"]
    return {
        "status": "ok",
        "customers": {"total": money(r["pending_not_due"] + r["overdue"]), "overdue": r["overdue"], "groups": groups("receivable")},
        "suppliers": {"total": money(p["pending_not_due"] + p["overdue"]), "overdue": p["overdue"], "groups": groups("payable")},
        "evidence": evidence(st["evidence"], "How we worked out what's owed"),
    }


def monthly_report(ds: Dataset) -> dict:
    s = financial_summary(ds.ledger, None, ds.as_of, ds.obligations, ds.as_of)
    if s["status"] != "ok":
        return {"status": "missing", "message": s["message"]}
    o = s["other_flows"]
    return {
        "status": "ok",
        "period": f"{day_full(s['period']['start'])} – {day_full(s['period']['end'])}",
        "totals": {"sales": s["revenue"], "costs": s["operating_expenses"], "profit": s["estimated_operating_profit"], "margin_pct": s["estimated_margin_pct"]},
        "months": [
            {"month": pd.Timestamp(m["month"] + "-01").strftime("%b %Y"), "sales": m["revenue"], "costs": m["operating_expenses"], "profit": m["estimated_operating_profit"], "cash_change": m["net_cash_movement"]}
            for m in s["monthly"]
        ][::-1],
        "outside_profit": [
            {"label": "Bought equipment / assets", "amount": o["capex"]},
            {"label": "Loans received", "amount": o["financing_in"]},
            {"label": "Loan EMIs paid", "amount": o["loan_repayments"]},
            {"label": "Taken out by owner", "amount": o["owner_drawings"]},
            {"label": "GST / TDS paid", "amount": o["tax_remitted"]},
        ],
        "evidence": evidence(s["evidence"], "How we worked out profit"),
    }


def reminder(ds: Dataset, customer: str) -> dict:
    st = obligations_status(ds.obligations, ds.as_of)
    if st["status"] != "ok":
        return {"status": "missing", "message": "No invoices uploaded."}
    inv = [i for i in st["receivables"]["overdue_items"] if i["counterparty"] == customer]
    if not inv:
        return {"status": "missing", "message": f"Nothing overdue from {customer}."}
    total = money(sum(i["amount"] for i in inv))
    lines = "\n".join(f"• {i['item_id']}: {fmt_inr(i['amount'])}, due {day_full(i['due_date'])}" for i in inv)
    text = (
        f"Namaste {customer} team,\n\nA friendly reminder from {ds.name.replace(' (fictional)', '')}. "
        f"The following invoice{'s are' if len(inv) > 1 else ' is'} now overdue:\n{lines}\n\n"
        f"Total: {fmt_inr(total)}. Could you please arrange the payment at the earliest? "
        "Do let us know if you need a copy of any invoice.\n\nThank you!"
    )
    return {"status": "ok", "customer": customer, "total": total, "invoices": inv, "text": text, "whatsapp": "https://wa.me/?text=" + quote(text)}


# ---------------------------------------------------------------- plan


def forecast(ds: Dataset, days: int = 90, late_days: int = 0, collect_pct: float = 100, count_overdue: bool = False, typical: bool = True, cushion: float | None = None) -> dict:
    pos = cash_position(ds.ledger, ds.balances, ds.as_of)
    if pos["status"] != "ok":
        return {"status": "needs_balance", "message": "Add your bank balance first — the forecast starts from your real cash."}
    buf = default_buffer(ds.ledger, ds.as_of) if cushion is None else float(cushion)
    f = forecast_cash_flow(ds.ledger, ds.balances, ds.obligations, ds.as_of, ForecastOptions(
        horizon_days=days, receivable_delay_days=late_days, receivable_collection_pct=collect_pct,
        include_overdue_receivables=count_overdue, include_run_rate=typical, min_buffer=buf))
    if f["first_negative_date"]:
        tone, head = "bad", f"Cash runs out on {day(f['first_negative_date'])}"
    elif f["first_date_below_buffer"]:
        tone, head = "caution", f"Cash dips below your cushion on {day(f['first_date_below_buffer'])}"
    else:
        tone, head = "good", f"Cash stays above {short(buf)} for the next {days} days"
    items = [i for i in f["scheduled_items"] if i["kind"] == "scheduled"]
    big = sorted([i for i in items if abs(i["amount"]) >= 25_000], key=lambda i: i["date"])[:14]
    return {
        "status": "ok",
        "tone": tone,
        "headline": head,
        "detail": f"Lowest point: {short(f['lowest_balance'])} on {day(f['lowest_balance_date'])}. Starting from {short(f['starting_cash'])} today.",
        "start": f["starting_cash"],
        "cushion": buf,
        "cushion_label": short(buf),
        "lowest": f["lowest_balance"],
        "lowest_date": f["lowest_balance_date"],
        "checkpoints": [{"days": c["days"], "date": c["date"], "balance": c["balance"], "label": short(c["balance"])} for c in f["checkpoints"]],
        "series": [{"date": d["date"], "balance": d["balance"]} for d in f["daily"]],
        "big_items": [{"date": i["date"], "day": day(i["date"]), "what": _plain_item(i["label"]), "category": i["category"], "amount": i["amount"]} for i in big],
        "not_counted": money(sum(e["amount"] for e in f["excluded_items"])),
        "evidence": evidence(f["evidence"], "How this forecast works"),
    }


def _scenario_text(key: str) -> str:
    sc = next(s for s in SCENARIOS if s.key == key)
    parts = []
    if sc.benefit_multiplier != 1:
        parts.append(f"the benefit is {'higher' if sc.benefit_multiplier > 1 else 'lower'} ({sc.benefit_multiplier:g}× your estimate)")
    if sc.benefit_delay_months:
        parts.append(f"it starts {sc.benefit_delay_months} months late")
    if sc.receivable_delay_days:
        parts.append(f"customers pay {sc.receivable_delay_days} days late")
    if sc.receivable_collection_pct < 100:
        parts.append(f"{100 - sc.receivable_collection_pct:g}% of what's owed isn't collected")
    if sc.include_overdue_receivables:
        parts.append("overdue customers pay up")
    return ("Assumes " + ", ".join(parts) + ".") if parts else "Assumes customers pay on time and the benefit is what you expect."


def afford(ds: Dataset, req: dict) -> dict:
    pos = cash_position(ds.ledger, ds.balances, ds.as_of)
    if pos["status"] != "ok":
        return {"status": "needs_balance", "message": "Add your bank balance first — FinPilot checks affordability against your real cash."}
    loan = req.get("paid_with") == "loan"
    if loan and (req.get("rate") in (None, "") or req.get("years") in (None, "")):
        return {"status": "needs_input", "message": "Enter the interest rate and number of years from your lender's quote. FinPilot doesn't guess loan terms."}
    try:
        p = Purchase(
            name=(req.get("name") or "This purchase").strip()[:80],
            cost=float(req["price"]),
            purchase_date=req.get("date") or str(ds.as_of.date()),
            financing="loan" if loan else "cash",
            down_payment_pct=float(req.get("down_payment_pct", 20)) if loan else 100.0,
            loan_rate_pct=float(req["rate"]) if loan else 0.0,
            tenure_months=int(round(float(req["years"]) * 12)) if loan else 12,
            monthly_benefit=float(req.get("monthly_benefit") or 0),
            benefit_start_months=int(req.get("benefit_start_months", 1)),
            monthly_running_cost=float(req.get("running_cost") or 0),
            one_time_costs=float(req.get("one_time_cost") or 0),
        )
    except (KeyError, TypeError, ValueError):
        return {"status": "invalid", "message": "Please enter a valid price and numbers."}
    if p.cost <= 0:
        return {"status": "invalid", "message": "Enter a price above zero."}
    cushion = req.get("cushion")
    r = simulate_purchase(ds.ledger, ds.balances, ds.obligations, ds.as_of, p, horizon_days=int(req.get("days", 180)),
                          min_buffer=float(cushion) if cushion not in (None, "") else None)
    if r["status"] != "ok":
        return {"status": "invalid", "message": r.get("message", "Couldn't run this.")}
    sc = {s["scenario"]: s for s in r["scenarios"]}
    base, down = sc["base"], sc["downside"]
    buf = r["buffer"]
    tone = r["verdict_tone"]
    if tone == "good":
        head = "Yes, you can afford it"
        detail = f"Even if the next few months are tough, your bank balance stays above {short(buf)} — one month of running costs. Lowest: {short(down['with_purchase']['lowest_balance'])} around {day(down['with_purchase']['lowest_balance_date'])}."
    elif base["with_purchase"]["lowest_balance"] >= buf:
        head = "Yes — but it's tight if business slows"
        detail = f"Most likely your balance stays above {short(buf)}. In tough months it could dip to {short(down['with_purchase']['lowest_balance'])} around {day(down['with_purchase']['lowest_balance_date'])}, below one month of running costs."
        if down["without_purchase"]["lowest_balance"] < buf:
            detail += " Tough months would be tight even without this purchase."
    elif tone == "caution":
        head = "Risky right now"
        detail = f"Even in the most likely case your balance falls to {short(base['with_purchase']['lowest_balance'])} around {day(base['with_purchase']['lowest_balance_date'])} — below one month of running costs ({short(buf)})."
    else:
        head = "Not right now"
        detail = f"Your bank balance would go below zero around {day(base['with_purchase']['first_negative_date'] or base['with_purchase']['lowest_balance_date'])} in the most likely case."
    return {
        "status": "ok",
        "tone": tone,
        "headline": head,
        "detail": detail,
        "cushion": buf,
        "cushion_label": short(buf),
        "upfront": r["upfront_cash"],
        "emi": r["emi"] or None,
        "total_interest": r["total_loan_interest"] or None,
        "payback_months": r["payback_months"],
        "months": p.tenure_months if loan else None,
        "today": pos["cash_balance"],
        "scenarios": [
            {
                "key": k, "name": SCENARIO_NAMES[k], "assumes": _scenario_text(k),
                "lowest": sc[k]["with_purchase"]["lowest_balance"], "lowest_date": sc[k]["with_purchase"]["lowest_balance_date"],
                "lowest_without": sc[k]["without_purchase"]["lowest_balance"],
                "end": sc[k]["with_purchase"]["end_balance"], "end_without": sc[k]["without_purchase"]["end_balance"],
                "below_cushion": sc[k]["with_purchase"]["first_date_below_buffer"], "negative": sc[k]["with_purchase"]["first_negative_date"],
                "series": [{"date": a["date"], "with": a["balance"], "without": b["balance"]} for a, b in zip(sc[k]["daily_with"], sc[k]["daily_without"])],
            }
            for k in ("base", "downside", "optimistic")
        ],
        "evidence": evidence(r["evidence"], "How we checked this"),
    }


# ---------------------------------------------------------------- records


def records(ds: Dataset, ids: list[str]) -> list[dict]:
    out = []
    led = ds.ledger[ds.ledger["txn_id"].isin(ids)]
    for r in led.sort_values("date").itertuples():
        out.append({"id": r.txn_id, "type": "transaction", "date": str(pd.Timestamp(r.date).date()), "title": r.description, "party": r.counterparty,
                    "category": r.category, "amount": float(r.amount), "direction": r.direction})
    if ds.obligations is not None and len(ds.obligations):
        ob = ds.obligations[ds.obligations["item_id"].isin(ids)]
        for r in ob.itertuples():
            out.append({"id": r.item_id, "type": "invoice" if r.kind == "receivable" else "bill", "date": str(pd.Timestamp(r.due_date).date()),
                        "title": r.description, "party": r.counterparty, "category": r.category, "amount": float(r.amount),
                        "direction": "in" if r.kind == "receivable" else "out", "status": r.status})
    return out
