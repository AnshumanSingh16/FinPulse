"""
Owner-facing views. Each function turns tested engine results into plain-language payloads for the
web app: a headline, the numbers behind it, and the evidence. No new financial logic lives here —
only selection, grouping and wording (English or Hindi) — so every figure still traces back to
finpilot.engine.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from finpilot.data import books
from finpilot.engine.budget import budget_status
from finpilot.engine.cash import cash_position, obligations_status, upcoming_payments
from finpilot.engine.common import fmt_inr, last_full_month, money, prepare_ledger
from finpilot.engine.decision import SCENARIOS, Purchase, default_buffer, simulate_purchase
from finpilot.engine.expenses import compare_expenses, unusual_transactions
from finpilot.engine.forecast import ForecastOptions, forecast_cash_flow
from finpilot.engine.summary import financial_summary

from . import i18n
from .dataset import Dataset
from .i18n import t

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


def day(d, lang: str = "en") -> str:
    return i18n.day(d, lang)


def day_full(d, lang: str = "en") -> str:
    return i18n.day_full(d, lang)


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


def _plain_item(label: str, lang: str = "en") -> str:
    """'SCH-0056 to Staff payroll' → 'Pay Staff payroll'; 'INV-0120 from Metro Foods' → 'From Metro Foods'."""
    if " to " in label:
        return t(lang, "fc.pay", name=label.split(" to ", 1)[1])
    if " from " in label:
        return t(lang, "fc.from", name=label.split(" from ", 1)[1])
    return label


# ---------------------------------------------------------------- shared pieces


def _cash_and_outlook(ds: Dataset, days: int = 90):
    pos = cash_position(ds.ledger, ds.balances, ds.as_of)
    buffer = default_buffer(ds.ledger, ds.as_of) if len(ds.ledger) else 0.0
    fc = None
    if pos["status"] == "ok":
        fc = forecast_cash_flow(ds.ledger, ds.balances, ds.obligations, ds.as_of, ForecastOptions(horizon_days=days, include_run_rate=True, min_buffer=buffer))
    return pos, buffer, fc


def _history(ds: Dataset, cash_now: float, days: int = 90) -> list[dict]:
    """Bank balance on each past day, worked back from today's balance: balance(d) = cash − Σ movements after d."""
    df = prepare_ledger(ds.ledger) if len(ds.ledger) else None
    start = ds.as_of - pd.Timedelta(days=days)
    daily = pd.Series(dtype=float)
    if df is not None:
        df = df[df["date"] <= ds.as_of]
        daily = df[df["date"] > start].groupby("date")["signed"].sum()
    out = []
    after = 0.0
    for d in pd.date_range(start, ds.as_of, freq="D")[::-1]:
        out.append({"date": str(d.date()), "balance": money(cash_now - after)})
        after += float(daily.get(d, 0.0))
    return out[::-1]


def status(pos: dict, fc: dict | None, buffer: float, lang: str = "en") -> dict:
    if pos["status"] != "ok":
        return {"tone": "neutral", "headline": t(lang, "st.no_balance.h"), "detail": t(lang, "st.no_balance.d")}
    if fc and fc["status"] == "ok" and fc["first_negative_date"]:
        return {"tone": "bad", "headline": t(lang, "st.negative.h", date=day(fc["first_negative_date"], lang)), "detail": t(lang, "st.negative.d")}
    if fc and fc["status"] == "ok" and fc["first_date_below_buffer"] and buffer:
        return {"tone": "caution", "headline": t(lang, "st.tight.h", date=day(fc["first_date_below_buffer"], lang)),
                "detail": t(lang, "st.tight.d", cushion=short(buffer), low=short(fc["lowest_balance"]), lowdate=day(fc["lowest_balance_date"], lang))}
    if not buffer:
        return {"tone": "neutral", "headline": t(lang, "st.nohist.h", cash=short(pos["cash_balance"])), "detail": t(lang, "st.nohist.d")}
    return {"tone": "good", "headline": t(lang, "st.good.h"), "detail": t(lang, "st.good.d", cash=short(pos["cash_balance"]), months=f"{pos['cash_balance'] / buffer:.1f}")}


def _month_periods(as_of: pd.Timestamp):
    this0, this1 = last_full_month(as_of)
    prev1 = this0 - pd.Timedelta(days=1)
    return (this0, this1), (prev1.replace(day=1), prev1)


def _summary_numbers(ds: Dataset, start, end, lang: str = "en") -> dict | None:
    s = financial_summary(ds.ledger, start, end) if len(ds.ledger) else {"status": "insufficient_data"}
    if s["status"] != "ok":
        return None
    return {
        "label": i18n.month(start, lang),
        "short_label": i18n.month(start, lang, year=False),
        "sales": s["revenue"],
        "costs": s["operating_expenses"],
        "profit": s["estimated_operating_profit"],
        "margin_pct": s["estimated_margin_pct"],
        "evidence": evidence(s["evidence"], t(lang, "ev.month_profit", month=i18n.month(start, lang, year=False))),
    }


# ---------------------------------------------------------------- home


def attention(ds: Dataset, pos: dict, fc: dict | None, buffer: float, db: Path | None = None, lang: str = "en") -> list[dict]:
    items: list[dict] = []
    L = lang
    if pos["status"] == "ok":
        for r in pos["reconciliation"]:
            if not r["reconciled"]:
                items.append({"id": f"recon-{r['as_of']}", "tone": "bad", "icon": "alert", "title": t(L, "att.recon.t"),
                              "body": t(L, "att.recon.b", date=day_full(r["as_of"], L), stated=short(r["stated_balance"]), computed=short(r["computed_from_ledger"])),
                              "action": {"type": "review", "label": t(L, "att.recon.a"), "ids": []}})
    if fc and fc["status"] == "ok" and buffer and (fc["first_negative_date"] or fc["first_date_below_buffer"]):
        neg = fc["first_negative_date"]
        items.append({"id": "cash-outlook", "tone": "bad" if neg else "caution", "icon": "trend",
                      "title": t(L, "att.cash_out.t" if neg else "att.cash_tight.t", date=day(neg or fc["first_date_below_buffer"], L)),
                      "body": t(L, "att.cash.b", low=short(fc["lowest_balance"]), date=day(fc["lowest_balance_date"], L)),
                      "action": {"type": "open", "label": t(L, "att.cash.a"), "href": "/plan/?tab=cash"}})

    proms = {p["party"]: p for p in books.promises(db, ds.book)} if db else {}
    obl = obligations_status(ds.obligations, ds.as_of)
    if obl["status"] == "ok":
        by_customer: dict[str, list[dict]] = {}
        for i in obl["receivables"]["overdue_items"]:
            by_customer.setdefault(i["counterparty"], []).append(i)
        ranked = sorted(by_customer.items(), key=lambda kv: -sum(i["amount"] for i in kv[1]))
        for name, inv in ranked[:3]:
            total = money(sum(i["amount"] for i in inv))
            oldest = max(i["days_overdue"] for i in inv)
            p = proms.get(name)
            if p and pd.Timestamp(p["date"]) < ds.as_of:
                items.append({"id": f"promise-{name}", "tone": "bad", "icon": "customer",
                              "title": t(L, "att.promise.t", name=name, amt=short(p["amount"]), date=day(p["date"], L)),
                              "body": t(L, "att.promise.b", due=short(total)),
                              "action": {"type": "remind", "label": t(L, "att.owed.a"), "customer": name}})
                continue
            items.append({"id": f"owed-{name}", "tone": "bad" if oldest > 30 else "caution", "icon": "customer",
                          "title": t(L, "att.owed.t", name=name, amt=short(total)), "body": t(L, "att.owed.b", n=len(inv), days=oldest),
                          "action": {"type": "remind", "label": t(L, "att.owed.a"), "customer": name}})
        for i in obl["payables"]["overdue_items"][:2]:
            items.append({"id": f"bill-{i['item_id']}", "tone": "caution", "icon": "bill",
                          "title": t(L, "att.bill.t", name=i["counterparty"], days=i["days_overdue"]),
                          "body": t(L, "att.bill.b", amt=short(i["amount"]), date=day(i["due_date"], L)),
                          "action": {"type": "todo", "label": t(L, "att.bill.a"), "text": t(L, "att.bill.todo", name=i["counterparty"], amt=fmt_inr(i["amount"]), id=i["item_id"])}})

    if db:
        bud = books.budgets(db, ds.book)
        if bud and len(ds.ledger):
            for r in budget_status(ds.ledger, bud, ds.as_of)["rows"]:
                if r["state"] == "over":
                    items.append({"id": f"budget-{r['category']}", "tone": "caution", "icon": "wallet",
                                  "title": t(L, "att.budget.t", cat=r["category"]), "body": t(L, "att.budget.b", spent=short(r["spent"]), limit=short(r["limit"])),
                                  "action": {"type": "open", "label": t(L, "att.budget.a"), "href": "/goals/"}})
    if len(ds.ledger):
        flags = unusual_transactions(ds.ledger, ds.as_of, lookback_days=90)["flags"]
        for f in [f for f in flags if f["type"] == "possible_duplicate"][:2]:
            items.append({"id": f"dup-{'-'.join(f['txn_ids'])}", "tone": "caution", "icon": "copy",
                          "title": t(L, "att.dup.t", name=f["counterparty"]), "body": t(L, "att.dup.b", n=len(f["txn_ids"]), amt=short(f["amount"]), date=day(f["date"], L)),
                          "action": {"type": "review", "label": t(L, "att.dup.a"), "ids": f["txn_ids"]}})
        unusual = sorted([f for f in flags if f["type"] == "outlier"], key=lambda f: -(f.get("excess") or f["amount"]))
        for f in unusual[:2]:
            times = f["reason"].split("×")[0].strip() if "×" in f["reason"] else "?"
            items.append({"id": f"odd-{'-'.join(f['txn_ids'])}", "tone": "info", "icon": "spark",
                          "title": t(L, "att.odd.t", cat=f["category"].lower(), amt=short(f["amount"])),
                          "body": t(L, "att.odd.b", party=f["counterparty"], date=day(f["date"], L), times=times),
                          "action": {"type": "review", "label": t(L, "att.odd.a"), "ids": f["txn_ids"]}})
        guessed = ds.ledger["category"].isin(["Uncategorised"]) | ds.ledger["reference"].astype(str).str.contains("auto:guess", na=False)
        if guessed.sum():
            items.append({"id": "review", "tone": "info", "icon": "tag", "title": t(L, "att.review.t", n=int(guessed.sum())), "body": t(L, "att.review.b"),
                          "action": {"type": "open", "label": t(L, "att.review.a"), "href": "/money/?tab=sort"}})
    return items


def home(ds: Dataset, db: Path | None = None, lang: str = "en") -> dict:
    L = lang
    pos, buffer, fc = _cash_and_outlook(ds)
    cash = {"known": pos["status"] == "ok"}
    if cash["known"]:
        c = pos["cash_balance"]
        cash.update({
            "amount": c, "label": short(c), "exact": fmt_inr(c),
            "months_of_costs": round(c / buffer, 1) if buffer else None,
            "cushion": buffer or None, "cushion_label": short(buffer) if buffer else None,
            "reconciled": bool(pos["reconciliation"]) and all(r["reconciled"] for r in pos["reconciliation"]),
            "history": _history(ds, c),
            "outlook": [{"date": d["date"], "balance": d["balance"]} for d in fc["daily"]] if fc and fc["status"] == "ok" else [],
            "in_90_days": fc["checkpoints"][min(2, len(fc["checkpoints"]) - 1)]["balance"] if fc and fc["status"] == "ok" else None,
            "evidence": evidence(pos["evidence"], t(L, "ev.cash")),
        })

    (t0, t1), (p0, p1) = _month_periods(ds.as_of)
    this, prev = _summary_numbers(ds, t0, t1, L), _summary_numbers(ds, p0, p1, L)
    if this is None:  # no complete month yet (e.g. a fresh book): show this month so far
        t0, t1 = ds.as_of.replace(day=1), ds.as_of
        p1 = t0 - pd.Timedelta(days=1)
        p0 = p1.replace(day=1)
        this, prev = _summary_numbers(ds, t0, t1, L), _summary_numbers(ds, p0, p1, L)
        if this:
            this["label"] = t(L, "month.so_far", month=i18n.month(t0, L, year=False))
    month = None
    if this:
        month = {**this, "previous": prev}
        if prev:
            month["change"] = {k: pct_change(this[k], prev[k]) for k in ("sales", "costs", "profit")}

    spending, insight = [], None
    if len(ds.ledger):
        cmp = compare_expenses(ds.ledger, (p0, p1), (t0, t1))
        if cmp["status"] == "ok":
            rows = sorted(cmp["by_category"], key=lambda r: -r["period_b"])
            spending = [{"category": r["category"], "amount": r["period_b"], "previous": r["period_a"], "change_pct": r["change_pct"]} for r in rows if r["period_b"] > 0][:6]
            tp = cmp["total_change_pct"]
            if tp is not None and abs(tp) >= 10:
                up = tp > 0
                mover = max(cmp["by_category"], key=lambda r: r["change"] if up else -r["change"])
                pm, tm = i18n.month(p0, L, year=False), i18n.month(t0, L, year=False)
                insight = {"tone": "caution" if up else "good",
                           "text": t(L, "ins.up" if up else "ins.down", pct=f"{abs(tp):.0f}", month=pm, cat=mover["category"].lower(), amt=short(abs(mover["change"]))),
                           "ask": t(L, "ins.ask.up" if up else "ins.ask.down", month=tm)}

    trend = []
    if len(ds.ledger):
        six = financial_summary(ds.ledger, (t0 - pd.DateOffset(months=5)).replace(day=1), t1)
        if six["status"] == "ok":
            trend = [{"month": i18n.MONTHS_HI_SHORT[int(m["month"][5:7]) - 1] if L == "hi" else pd.Timestamp(m["month"] + "-01").strftime("%b"),
                      "sales": m["revenue"], "costs": m["operating_expenses"], "profit": m["estimated_operating_profit"]} for m in six["monthly"]]

    up = upcoming_payments(ds.obligations, ds.as_of, 14)
    upcoming = [{"date": i["due_date"], "day": day(i["due_date"], L), "name": i["counterparty"], "what": i["description"], "amount": i["amount"]}
                for i in (up["upcoming"] if up["status"] == "ok" else [])]
    return {
        "business": ds.name, "is_demo": ds.is_demo, "as_of": str(ds.as_of.date()), "as_of_label": day_full(ds.as_of, L),
        "status": status(pos, fc, buffer, L), "cash": cash, "month": month, "insight": insight,
        "attention": attention(ds, pos, fc, buffer, db, L), "spending": spending, "trend": trend, "upcoming": upcoming,
        "upcoming_total": up.get("upcoming_total") if up["status"] == "ok" else None,
    }


# ---------------------------------------------------------------- money


def transactions(ds: Dataset, q: str = "", direction: str = "", category: str = "", ids: list[str] | None = None, limit: int = 100, offset: int = 0, lang: str = "en") -> dict:
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
            {"id": r.txn_id, "date": str(r.date.date()), "day": day_full(r.date, lang), "description": r.description, "party": r.counterparty,
             "category": r.category, "direction": r.direction, "amount": float(r.amount), "mode": getattr(r, "payment_mode", None) or None,
             "guess": "auto:guess" in str(getattr(r, "reference", "") or ""), "editable": str(r.txn_id).startswith("E")}
            for r in page.itertuples()
        ],
    }


def owed(ds: Dataset, lang: str = "en") -> dict:
    o = ds.obligations
    st = obligations_status(o, ds.as_of)
    if st["status"] != "ok":
        return {"status": "missing", "message": t(lang, "owed.missing")}
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
            g["items"].append({"id": r.item_id, "what": r.description, "amount": float(r.amount), "due": str(r.due_date.date()), "due_label": day_full(r.due_date, lang),
                               "state": "overdue" if late > 0 else ("due_soon" if late >= -7 else "upcoming"), "days_late": max(late, 0), "days_left": max(-late, 0)})
        res = [{**g, "total": money(g["total"]), "overdue": money(g["overdue"])} for g in out.values()]
        return sorted(res, key=lambda g: (-g["overdue"], -g["total"]))

    r, p = st["receivables"], st["payables"]
    return {
        "status": "ok",
        "customers": {"total": money(r["pending_not_due"] + r["overdue"]), "overdue": r["overdue"], "groups": groups("receivable")},
        "suppliers": {"total": money(p["pending_not_due"] + p["overdue"]), "overdue": p["overdue"], "groups": groups("payable")},
        "evidence": evidence(st["evidence"], t(lang, "ev.owed")),
    }


def monthly_report(ds: Dataset, lang: str = "en") -> dict:
    s = financial_summary(ds.ledger, None, ds.as_of, ds.obligations, ds.as_of) if len(ds.ledger) else {"status": "x", "message": t(lang, "st.nohist.d")}
    if s["status"] != "ok":
        return {"status": "missing", "message": s["message"]}
    o = s["other_flows"]
    return {
        "status": "ok",
        "period": f"{day_full(s['period']['start'], lang)} – {day_full(s['period']['end'], lang)}",
        "totals": {"sales": s["revenue"], "costs": s["operating_expenses"], "profit": s["estimated_operating_profit"], "margin_pct": s["estimated_margin_pct"]},
        "months": [
            {"month": i18n.month(m["month"] + "-01", lang), "key": m["month"], "sales": m["revenue"], "costs": m["operating_expenses"], "profit": m["estimated_operating_profit"],
             "cash_change": m["net_cash_movement"]}
            for m in s["monthly"]
        ][::-1],
        "outside_profit": [
            {"label": t(lang, "rep.capex"), "amount": o["capex"]},
            {"label": t(lang, "rep.loan_in"), "amount": o["financing_in"]},
            {"label": t(lang, "rep.emi"), "amount": o["loan_repayments"]},
            {"label": t(lang, "rep.drawings"), "amount": o["owner_drawings"]},
            {"label": t(lang, "rep.tax"), "amount": o["tax_remitted"]},
        ],
        "evidence": evidence(s["evidence"], t(lang, "ev.profit")),
    }


# ---------------------------------------------------------------- plan


def forecast(ds: Dataset, days: int = 90, late_days: int = 0, collect_pct: float = 100, count_overdue: bool = False, typical: bool = True,
             cushion: float | None = None, lang: str = "en") -> dict:
    L = lang
    pos = cash_position(ds.ledger, ds.balances, ds.as_of)
    if pos["status"] != "ok":
        return {"status": "needs_balance", "message": t(L, "fc.need_balance")}
    buf = (default_buffer(ds.ledger, ds.as_of) if len(ds.ledger) else 0.0) if cushion is None else float(cushion)
    f = forecast_cash_flow(ds.ledger, ds.balances, ds.obligations, ds.as_of, ForecastOptions(
        horizon_days=days, receivable_delay_days=late_days, receivable_collection_pct=collect_pct,
        include_overdue_receivables=count_overdue, include_run_rate=typical, min_buffer=buf))
    if not buf and not f["first_negative_date"]:
        tone, head = "neutral", t(L, "fc.neutral", cash=short(f["starting_cash"]))
    elif f["first_negative_date"]:
        tone, head = "bad", t(L, "fc.bad", date=day(f["first_negative_date"], L))
    elif f["first_date_below_buffer"]:
        tone, head = "caution", t(L, "fc.caution", date=day(f["first_date_below_buffer"], L))
    else:
        tone, head = "good", t(L, "fc.good", cushion=short(buf), days=days)
    items = [i for i in f["scheduled_items"] if i["kind"] == "scheduled"]
    big = sorted([i for i in items if abs(i["amount"]) >= 25_000], key=lambda i: i["date"])[:14]
    return {
        "status": "ok", "tone": tone, "headline": head,
        "detail": t(L, "fc.detail", low=short(f["lowest_balance"]), date=day(f["lowest_balance_date"], L), start=short(f["starting_cash"])),
        "start": f["starting_cash"], "cushion": buf, "cushion_label": short(buf), "lowest": f["lowest_balance"], "lowest_date": f["lowest_balance_date"],
        "checkpoints": [{"days": c["days"], "date": c["date"], "balance": c["balance"], "label": short(c["balance"])} for c in f["checkpoints"]],
        "series": [{"date": d["date"], "balance": d["balance"]} for d in f["daily"]],
        "big_items": [{"date": i["date"], "day": day(i["date"], L), "what": _plain_item(i["label"], L), "category": i["category"], "amount": i["amount"]} for i in big],
        "not_counted": money(sum(e["amount"] for e in f["excluded_items"])),
        "evidence": evidence(f["evidence"], t(L, "ev.forecast")),
    }


def _scenario_text(key: str, lang: str = "en") -> str:
    sc = next(s for s in SCENARIOS if s.key == key)
    parts = []
    if sc.benefit_multiplier != 1:
        parts.append(t(lang, "sc.p.mult_hi" if sc.benefit_multiplier > 1 else "sc.p.mult_lo", x=f"{sc.benefit_multiplier:g}"))
    if sc.benefit_delay_months:
        parts.append(t(lang, "sc.p.delay", n=sc.benefit_delay_months))
    if sc.receivable_delay_days:
        parts.append(t(lang, "sc.p.late", n=sc.receivable_delay_days))
    if sc.receivable_collection_pct < 100:
        parts.append(t(lang, "sc.p.loss", n=f"{100 - sc.receivable_collection_pct:g}"))
    if sc.include_overdue_receivables:
        parts.append(t(lang, "sc.p.overdue"))
    return t(lang, "sc.assumes", parts=t(lang, "sep").join(parts)) if parts else t(lang, "sc.default")


def afford(ds: Dataset, req: dict, lang: str = "en") -> dict:
    L = lang
    pos = cash_position(ds.ledger, ds.balances, ds.as_of)
    if pos["status"] != "ok":
        return {"status": "needs_balance", "message": t(L, "af.need_balance")}
    loan = req.get("paid_with") == "loan"
    if loan and (req.get("rate") in (None, "") or req.get("years") in (None, "")):
        return {"status": "needs_input", "message": t(L, "af.need_loan")}
    try:
        p = Purchase(
            name=(req.get("name") or "This purchase").strip()[:80], cost=float(req["price"]), purchase_date=req.get("date") or str(ds.as_of.date()),
            financing="loan" if loan else "cash", down_payment_pct=float(req.get("down_payment_pct", 20)) if loan else 100.0,
            loan_rate_pct=float(req["rate"]) if loan else 0.0, tenure_months=int(round(float(req["years"]) * 12)) if loan else 12,
            monthly_benefit=float(req.get("monthly_benefit") or 0), benefit_start_months=int(req.get("benefit_start_months", 1)),
            monthly_running_cost=float(req.get("running_cost") or 0), one_time_costs=float(req.get("one_time_cost") or 0),
        )
    except (KeyError, TypeError, ValueError):
        return {"status": "invalid", "message": t(L, "af.invalid")}
    if p.cost <= 0:
        return {"status": "invalid", "message": t(L, "af.invalid")}
    cushion = req.get("cushion")
    r = simulate_purchase(ds.ledger, ds.balances, ds.obligations, ds.as_of, p, horizon_days=int(req.get("days", 180)),
                          min_buffer=float(cushion) if cushion not in (None, "") else None)
    if r["status"] != "ok":
        return {"status": "invalid", "message": r.get("message", t(L, "af.invalid"))}
    sc = {s["scenario"]: s for s in r["scenarios"]}
    base, down = sc["base"], sc["downside"]
    buf = r["buffer"]
    tone = r["verdict_tone"]
    dw, bw = down["with_purchase"], base["with_purchase"]
    if tone == "good":
        head, detail = t(L, "af.good.h"), t(L, "af.good.d", cushion=short(buf), low=short(dw["lowest_balance"]), date=day(dw["lowest_balance_date"], L))
    elif bw["lowest_balance"] >= buf:
        head = t(L, "af.tight.h")
        detail = t(L, "af.tight.d", cushion=short(buf), low=short(dw["lowest_balance"]), date=day(dw["lowest_balance_date"], L))
        if down["without_purchase"]["lowest_balance"] < buf:
            detail += t(L, "af.tight.extra")
    elif tone == "caution":
        head, detail = t(L, "af.risky.h"), t(L, "af.risky.d", low=short(bw["lowest_balance"]), date=day(bw["lowest_balance_date"], L), cushion=short(buf))
    else:
        head, detail = t(L, "af.bad.h"), t(L, "af.bad.d", date=day(bw["first_negative_date"] or bw["lowest_balance_date"], L))
    return {
        "status": "ok", "tone": tone, "headline": head, "detail": detail, "cushion": buf, "cushion_label": short(buf),
        "upfront": r["upfront_cash"], "emi": r["emi"] or None, "total_interest": r["total_loan_interest"] or None,
        "payback_months": r["payback_months"], "months": p.tenure_months if loan else None, "today": pos["cash_balance"],
        "scenarios": [
            {"key": k, "name": t(L, f"sc.{k}"), "assumes": _scenario_text(k, L),
             "lowest": sc[k]["with_purchase"]["lowest_balance"], "lowest_date": sc[k]["with_purchase"]["lowest_balance_date"],
             "lowest_without": sc[k]["without_purchase"]["lowest_balance"], "end": sc[k]["with_purchase"]["end_balance"], "end_without": sc[k]["without_purchase"]["end_balance"],
             "below_cushion": sc[k]["with_purchase"]["first_date_below_buffer"], "negative": sc[k]["with_purchase"]["first_negative_date"],
             "series": [{"date": a["date"], "with": a["balance"], "without": b["balance"]} for a, b in zip(sc[k]["daily_with"], sc[k]["daily_without"])]}
            for k in ("base", "downside", "optimistic")
        ],
        "evidence": evidence(r["evidence"], t(L, "ev.afford")),
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
