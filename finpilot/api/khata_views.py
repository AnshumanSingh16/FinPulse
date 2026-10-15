"""Customers & suppliers (udhaar khata), quick-entry helpers and category review, for the web app."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

import pandas as pd

from finpilot.data import books
from finpilot.data.schema import CATEGORY_CLASS
from finpilot.engine.common import fmt_inr, money

from .dataset import Dataset
from .views import day, day_full, short

SIDES = {"customers": "receivable", "suppliers": "payable"}


def _obl(ds: Dataset) -> pd.DataFrame:
    o = ds.obligations
    if o is None or not len(o):
        return pd.DataFrame(columns=["item_id", "kind", "counterparty", "description", "category", "amount", "issue_date", "due_date", "status", "paid_date"])
    o = o.copy()
    for c in ("issue_date", "due_date", "paid_date"):
        o[c] = pd.to_datetime(o[c])
    return o


def reliability(paid: pd.DataFrame) -> dict:
    """How promptly bills were settled: share paid by the due date and average days late."""
    p = paid.dropna(subset=["paid_date", "due_date"])
    if len(p) < 2:
        return {"label": "New", "tone": "neutral", "on_time_pct": None, "avg_days_late": None, "count": int(len(p))}
    late = (p["paid_date"] - p["due_date"]).dt.days.clip(lower=0)
    on_time = round(float((late == 0).mean()) * 100)
    avg = round(float(late.mean()), 1)
    if on_time >= 80:
        label, tone = "Pays on time", "good"
    elif on_time >= 50:
        label, tone = "Sometimes late", "caution"
    else:
        label, tone = "Often late", "bad"
    return {"label": label, "tone": tone, "on_time_pct": on_time, "avg_days_late": avg, "count": int(len(p))}


def people(ds: Dataset, db: Path, side: str = "customers", lang: str = "en") -> dict:
    kind = SIDES[side]
    o = _obl(ds)
    o = o[o["kind"] == kind]
    phones = books.contacts(db, ds.book)
    proms = {p["party"]: p for p in books.promises(db, ds.book)}
    led = ds.ledger
    direction = "in" if side == "customers" else "out"
    out = []
    for name, g in o.groupby("counterparty"):
        pend = g[g["status"] == "pending"]
        overdue = pend[pend["due_date"] < ds.as_of]
        last = led[(led["counterparty"] == name) & (led["direction"] == direction)]
        last_pay = pd.to_datetime(last["date"]).max() if len(last) else None
        pr = proms.get(name)
        promise = None
        if pr:
            broken = pd.Timestamp(pr["date"]) < ds.as_of and len(pend) > 0
            promise = {"amount": pr["amount"], "date": pr["date"], "day": day(pr["date"], lang), "note": pr["note"], "broken": bool(broken)}
        out.append({
            "name": name,
            "outstanding": money(pend["amount"].sum()),
            "overdue": money(overdue["amount"].sum()),
            "open_items": int(len(pend)),
            "oldest_days_late": int((ds.as_of - overdue["due_date"].min()).days) if len(overdue) else 0,
            "next_due": day(pend["due_date"].min(), lang) if len(pend) and not len(overdue) else None,
            "last_payment": day_full(last_pay, lang) if last_pay is not None and not pd.isna(last_pay) else None,
            "reliability": reliability(g[g["status"] == "paid"]),
            "phone": phones.get(name),
            "promise": promise,
        })
    out.sort(key=lambda r: (-r["overdue"], -r["outstanding"], r["name"]))
    active = [r for r in out if r["outstanding"] > 0]
    settled = [r for r in out if r["outstanding"] <= 0]
    total = money(sum(r["outstanding"] for r in out))
    overdue_total = money(sum(r["overdue"] for r in out))
    return {"side": side, "total": total, "overdue": overdue_total, "count": len(active), "people": active + settled}


def person(ds: Dataset, db: Path, name: str, lang: str = "en") -> dict:
    o = _obl(ds)
    o = o[o["counterparty"] == name]
    led = ds.ledger[ds.ledger["counterparty"] == name].copy()
    led["date"] = pd.to_datetime(led["date"])
    kind = "receivable" if (o["kind"] == "receivable").any() or not len(o) else "payable"
    timeline = []
    for r in o.itertuples():
        timeline.append({"id": r.item_id, "date": str(r.issue_date.date()) if not pd.isna(r.issue_date) else str(r.due_date.date()),
                         "type": "udhaar" if kind == "receivable" else "bill", "title": r.description or ("Invoice" if kind == "receivable" else "Bill"),
                         "amount": float(r.amount), "status": r.status, "due": day_full(r.due_date, lang),
                         "late_days": int((ds.as_of - r.due_date).days) if r.status == "pending" and r.due_date < ds.as_of else 0})
    for r in led.itertuples():
        timeline.append({"id": r.txn_id, "date": str(r.date.date()), "type": "payment_in" if r.direction == "in" else "payment_out",
                         "title": r.description, "amount": float(r.amount), "status": "done", "due": None, "late_days": 0})
    timeline.sort(key=lambda x: (x["date"], x["id"]), reverse=True)
    pend = o[o["status"] == "pending"]
    phones = books.contacts(db, ds.book)
    pr = next((p for p in books.promises(db, ds.book) if p["party"] == name), None)
    return {
        "name": name,
        "kind": "customer" if kind == "receivable" else "supplier",
        "outstanding": money(pend["amount"].sum()),
        "overdue": money(pend.loc[pend["due_date"] < ds.as_of, "amount"].sum()),
        "total_business": money(led["amount"].sum()),
        "reliability": reliability(o[o["status"] == "paid"]),
        "phone": phones.get(name),
        "promise": pr,
        "timeline": [t | {"day": day_full(t["date"], lang)} for t in timeline[:80]],
    }


def reminder_text(ds: Dataset, name: str, items: list[dict], lang: str = "en") -> str:
    shop = ds.name.replace(" (fictional)", "")
    total = money(sum(i["amount"] for i in items))
    if lang == "hi":
        lines = "\n".join(f"• {i['item_id']}: {fmt_inr(i['amount'])}, देय {day_full(i['due_date'], 'hi')}" for i in items)
        return (f"नमस्ते {name} जी,\n\n{shop} की ओर से एक विनम्र याद दिलाना। ये बिल अब बकाया हैं:\n{lines}\n\n"
                f"कुल: {fmt_inr(total)}. कृपया जल्द से जल्द भुगतान कर दें। किसी बिल की कॉपी चाहिए तो बताइए।\n\nधन्यवाद!")
    lines = "\n".join(f"• {i['item_id']}: {fmt_inr(i['amount'])}, due {day_full(i['due_date'])}" for i in items)
    return (f"Namaste {name} team,\n\nA friendly reminder from {shop}. The following "
            f"{'invoices are' if len(items) > 1 else 'invoice is'} now overdue:\n{lines}\n\n"
            f"Total: {fmt_inr(total)}. Could you please arrange the payment at the earliest? "
            "Do let us know if you need a copy of any invoice.\n\nThank you!")


def whatsapp(text: str, phone: str | None) -> str:
    return f"https://wa.me/{phone or ''}?text={quote(text)}"


def reminders(ds: Dataset, db: Path, lang: str = "en", only: str | None = None) -> list[dict]:
    o = _obl(ds)
    od = o[(o["kind"] == "receivable") & (o["status"] == "pending") & (o["due_date"] < ds.as_of)]
    phones = books.contacts(db, ds.book)
    out = []
    for name, g in od.groupby("counterparty"):
        if only and name != only:
            continue
        items = [{"item_id": r.item_id, "amount": float(r.amount), "due_date": str(r.due_date.date())} for r in g.sort_values("due_date").itertuples()]
        text = reminder_text(ds, name, items, lang)
        out.append({"customer": name, "total": money(g["amount"].sum()), "invoices": items, "text": text,
                    "phone": phones.get(name), "whatsapp": whatsapp(text, phones.get(name)),
                    "oldest_days_late": int((ds.as_of - g["due_date"].min()).days)})
    out.sort(key=lambda r: -r["total"])
    return out


def categories(ds: Dataset) -> list[dict]:
    """Categories for pickers: the known ones plus any in the book."""
    names = {c.title() if c.islower() else c for c in CATEGORY_CLASS} | set(ds.ledger["category"].dropna().unique())
    fixed = {"Gst Payment": "GST Payment", "Tds Payment": "TDS Payment", "Loan Emi": "Loan EMI", "Sales - B2B": "Sales - B2B"}
    names = {fixed.get(n, n) for n in names}
    out = []
    for n in sorted(names, key=str.lower):
        cls = CATEGORY_CLASS.get(n.lower(), "unclassified")
        out.append({"name": n, "type": "in" if cls in ("revenue", "financing_in", "other_in") else "out" if cls != "transfer" else "both"})
    return out


def review(ds: Dataset, db: Path) -> dict:
    """Bank lines that need a category: uncategorised, plus incoming money that was only guessed as sales."""
    led = ds.ledger
    mask = led["category"].isin(["Uncategorised", "Unknown", ""]) | (led["reference"].astype(str).str.contains("auto:guess", na=False))
    rows = led[mask]
    groups = []
    for (party, direction), g in rows.groupby(["counterparty", "direction"]):
        groups.append({"party": party, "direction": direction, "count": int(len(g)), "total": money(g["amount"].sum()),
                       "current": g["category"].iloc[0], "ids": g["txn_id"].tolist()[:200],
                       "example": str(g["description"].iloc[0])[:80]})
    groups.sort(key=lambda r: -r["total"])
    return {"count": int(len(rows)), "groups": groups[:50]}
