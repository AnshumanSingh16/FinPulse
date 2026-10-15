"""Views for the smart features: health score, weekly story, budgets & goals, calendar & GST, what-ifs, reports."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from finpilot.data import books
from finpilot.engine import budget as bud
from finpilot.engine import calendar_gst as cg
from finpilot.engine import reports, whatif
from finpilot.engine.health import health_score
from finpilot.engine.story import weekly_story

from . import i18n
from .dataset import Dataset
from .i18n import t
from .views import evidence, short

TIPS_FOR = {"cash": "/plan/?tab=cash", "profit": "/plan/?tab=price", "collections": "/khata/", "bills": "/khata/?side=suppliers", "momentum": "/plan/?tab=discount"}


_HEALTH_CACHE: dict = {}


def _fingerprint(ds: Dataset) -> tuple:
    """Changes whenever the book's data changes (entries, payments, uploads)."""
    def f(df, cols):
        if df is None or not len(df):
            return (0,)
        return (len(df),) + tuple(round(float(pd.to_numeric(df[c], errors="coerce").fillna(0).sum()), 2) if c in ("amount", "balance") else
                                   hash(tuple(df[c].astype(str))) for c in cols)
    return (ds.book, str(ds.as_of.date()), f(ds.ledger, ["amount", "txn_id", "category"]),
            f(ds.obligations, ["amount", "status", "item_id"]), f(ds.balances, ["balance", "as_of"]))


def health(ds: Dataset, lang: str = "en") -> dict:
    L = lang
    if not len(ds.ledger):
        return {"status": "empty"}
    key = _fingerprint(ds)
    if key not in _HEALTH_CACHE:
        if len(_HEALTH_CACHE) > 8:
            _HEALTH_CACHE.clear()
        _HEALTH_CACHE[key] = health_score(ds.ledger, ds.balances, ds.obligations, ds.as_of)
    import copy

    h = copy.deepcopy(_HEALTH_CACHE[key])
    comps = []
    for c in h["components"]:
        k = c["key"]
        value_text = t(L, "hs.unknown") if c["value"] is None else t(L, f"hs.{k}.v", v=f"{c['value']:g}")
        comps.append(c | {"label": t(L, f"hs.{k}"), "text": value_text, "tip": t(L, f"hs.{k}.tip") if c["status"] in ("bad", "caution", "unknown") else t(L, "hs.good"),
                          "href": TIPS_FOR[k]})
    weakest = sorted([c for c in comps if c["status"] != "good"], key=lambda c: c["points"])
    hist = h.get("history", [])
    change = hist[-1]["score"] - hist[-2]["score"] if len(hist) >= 2 else None
    for x in hist:
        x["label"] = i18n.MONTHS_HI_SHORT[int(x["date"][5:7]) - 1] if L == "hi" else x["month"]
    return {"status": "ok", "score": h["score"], "grade": t(L, f"hs.grade.{h['grade']}"), "grade_key": h["grade"], "components": comps,
            "focus": weakest[0] if weakest else None, "history": hist, "change": change, "evidence": evidence(h["evidence"], t(L, "ev.health"))}


def story(ds: Dataset, lang: str = "en") -> dict:
    L = lang
    s = weekly_story(ds.ledger, ds.obligations, ds.as_of)
    if s["status"] != "ok" or not s["this"]["count"]:
        return {"status": "empty", "cards": [{"kind": "empty", "title": t(L, "story.empty"), "body": ""}]}
    this, prev = s["this"], s["previous"]
    cards = []
    if prev["sales"]:
        ch = (this["sales"] - prev["sales"]) / prev["sales"] * 100
        vs = t(L, "story.sales.vs_up" if ch >= 0 else "story.sales.vs_down", pct=f"{abs(ch):.0f}", prev=short(prev["sales"]))
    else:
        ch, vs = None, t(L, "story.sales.vs_none")
    cards.append({"kind": "sales", "title": t(L, "story.sales", amt=short(this["sales"])), "body": vs, "value": this["sales"], "change": round(ch, 1) if ch is not None else None})
    if s["best_day"]:
        cards.append({"kind": "best_day", "title": t(L, "story.best", day=i18n.weekday(s["best_day"]["date"], L)), "body": t(L, "story.best.b", amt=short(s["best_day"]["amount"]))})
    if s["top_customer"]:
        cards.append({"kind": "top_customer", "title": t(L, "story.top", name=s["top_customer"]["name"]), "body": t(L, "story.top.b", amt=short(s["top_customer"]["amount"]))})
    if s["collected"]:
        cards.append({"kind": "collected", "title": t(L, "story.collect", amt=short(s["collected"])), "body": t(L, "story.collect.b", n=s["invoices_cleared"])})
    if s["biggest_expense"]:
        b = s["biggest_expense"]
        cards.append({"kind": "spend", "title": t(L, "story.spend", amt=short(b["amount"])), "body": t(L, "story.spend.b", what=b["what"], party=b["party"]), "ids": [b["id"]]})
    if s["udhaar_given"]:
        cards.append({"kind": "udhaar", "title": t(L, "story.udhaar", amt=short(s["udhaar_given"])), "body": t(L, "story.udhaar.b")})
    net = s["net"]
    cards.append({"kind": "net", "title": t(L, "story.net_pos" if net >= 0 else "story.net_neg", amt=short(abs(net))),
                  "body": t(L, "story.net.b", inn=short(this["money_in"]), out=short(this["money_out"])), "positive": net >= 0})
    return {"status": "ok", "range": f"{i18n.day(s['period'][0], L)} – {i18n.day(s['period'][1], L)}", "title": t(L, "story.title"), "cards": cards,
            "this": this, "previous": prev, "top_costs": s["top_costs"]}


def budgets(ds: Dataset, db: Path, lang: str = "en") -> dict:
    limits = books.budgets(db, ds.book)
    suggested = bud.suggest_budgets(ds.ledger, ds.as_of) if len(ds.ledger) else {}
    st = bud.budget_status(ds.ledger, limits, ds.as_of) if limits else None
    if st:
        st["month"] = i18n.month(ds.as_of, lang)
    return {"limits": limits, "status": st, "suggested": suggested}


def goals(ds: Dataset, db: Path) -> list[dict]:
    return [bud.goal_plan(g, ds.as_of) for g in books.goals(db, ds.book)]


def calendar(ds: Dataset, db: Path, year: int, month: int, lang: str = "en") -> dict:
    st = books.settings(db, ds.book)
    c = cg.month_calendar(ds.ledger, ds.obligations, ds.as_of, year, month, st["gst_filing"], st["gst_registered"] == "yes")
    for d in c["days"]:
        for e in d["events"]:
            if e["kind"] == "tax":
                e["title"] = t(lang, f"cal.{e['title']}")
                e["detail"] = t(lang, "cal.typical")
            elif e["kind"] == "expected":
                e["detail"] = t(lang, "cal.expected", party=e["detail"].split("to ", 1)[-1].split(" around")[0], day=d["day"])
    c["label"] = i18n.month(pd.Timestamp(year=year, month=month, day=1), lang)
    c["today"] = str(ds.as_of.date())
    # GST set-aside for last month and this month so far
    first = pd.Timestamp(year=year, month=month, day=1)
    end = min(first + pd.offsets.MonthEnd(0), ds.as_of)
    if end >= first and len(ds.ledger) and st["gst_registered"] == "yes":
        g = cg.gst_estimate(ds.ledger, first, end, float(st["gst_rate_sales"]), float(st["gst_rate_purchases"]))
        g["evidence"] = evidence(g["evidence"], t(lang, "ev.gst"))
        c["gst"] = g
    c["settings"] = st
    return c


def whatifs(ds: Dataset, kind: str, p: dict, lang: str = "en") -> dict:
    f = lambda k, d=0.0: float(p.get(k) if p.get(k) not in (None, "") else d)  # noqa: E731
    if not len(ds.ledger):
        return {"status": "insufficient_data", "message": t(lang, "st.nohist.d")}
    if kind == "price":
        r = whatif.price_change(ds.ledger, ds.as_of, f("price_pct", 5), f("volume_pct", 0))
    elif kind == "discount":
        r = whatif.discount(ds.ledger, ds.as_of, f("discount_pct", 10), f("uplift_pct", 15), int(f("weeks", 4)))
    elif kind == "hire":
        r = whatif.hire(ds.ledger, ds.balances, ds.obligations, ds.as_of, f("salary", 15000), f("extra_sales", 0), int(f("start_months", 1)), f("one_time", 0))
    elif kind == "loan":
        r = whatif.loan(ds.ledger, ds.balances, ds.obligations, ds.as_of, f("amount", 500000), f("rate", 12), f("years", 3))
    else:
        return {"status": "invalid", "message": "Unknown simulator."}
    if "evidence" in r:
        r["evidence"] = evidence(r["evidence"], t(lang, "ev.whatif"))
    return r


def report_monthly(ds: Dataset, db: Path, year: int, month: int, lang: str = "en") -> dict:
    st = books.settings(db, ds.book)
    r = reports.monthly(ds.ledger, ds.balances, ds.obligations, ds.as_of, year, month, (float(st["gst_rate_sales"]), float(st["gst_rate_purchases"])))
    if r["status"] == "ok":
        r["label"] = i18n.month(pd.Timestamp(year=year, month=month, day=1), lang)
        r["evidence"] = evidence(r["evidence"], t(lang, "ev.profit"))
        r["gst"]["evidence"] = evidence(r["gst"]["evidence"], t(lang, "ev.gst"))
        r["business"] = ds.name
    return r


def report_loan(ds: Dataset, lang: str = "en") -> dict:
    r = reports.loan_readiness(ds.ledger, ds.balances, ds.obligations, ds.as_of)
    if r["status"] == "ok":
        r["evidence"] = evidence(r["evidence"], t(lang, "ev.profit"))
        r["business"] = ds.name
        for m in r["monthly"]:
            m["label"] = i18n.month(m["month"] + "-01", lang, year=False)
    return r


def months_available(ds: Dataset, lang: str = "en") -> list[dict]:
    if not len(ds.ledger):
        return []
    ms = pd.to_datetime(ds.ledger["date"]).dt.to_period("M").unique()
    return [{"key": str(m), "label": i18n.month(m.to_timestamp(), lang)} for m in sorted(ms, reverse=True)]
