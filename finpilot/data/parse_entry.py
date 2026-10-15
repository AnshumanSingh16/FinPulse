"""
Understand a quick entry typed (or spoken) in plain English or Hinglish, e.g.

    "sold masala to Ravi 2500 cash"         → sale ₹2,500, party Ravi, cash
    "Ravi ko 3000 udhaar"                   → udhaar given to Ravi ₹3,000
    "Ravi ne 1500 diye upi"                 → payment received from Ravi ₹1,500, UPI
    "paid rent 55000"                       → expense ₹55,000, Rent
    "bijli bill 4200"                       → expense ₹4,200, Electricity
    "bill from Kisan Agro 40k due 20 oct"   → supplier bill ₹40,000 due 20 Oct

This is a deterministic parser. It returns a draft for the owner to confirm, never a saved entry.
"""

from __future__ import annotations

import re

import pandas as pd

from finpilot.engine.categorize import categorize

AMOUNT = re.compile(r"(?:₹|rs\.?|inr)?\s*(\d[\d,]*(?:\.\d+)?)\s*(लाख|करोड़|करोड|हज़ार|हजार|k|lakh|lac|l|thousand|hazaar|hazar|cr|crore)?(?!\w)", re.I)
UNITS = {"k": 1e3, "thousand": 1e3, "hazaar": 1e3, "hazar": 1e3, "lakh": 1e5, "lac": 1e5, "l": 1e5, "cr": 1e7, "crore": 1e7, "लाख": 1e5, "करोड़": 1e7, "करोड": 1e7, "हज़ार": 1e3, "हजार": 1e3}
MODES = {"cash": "cash", "nakad": "cash", "upi": "upi", "gpay": "upi", "google pay": "upi", "phonepe": "upi", "paytm": "upi", "bhim": "upi",
         "bank": "bank", "neft": "bank", "imps": "bank", "rtgs": "bank", "transfer": "bank", "card": "card", "cheque": "cheque", "check": "cheque"}

KIND_WORDS = [
    ("credit_sale", r"\b(udhaar|udhar|udhari|on credit|credit pe|credit par|baaki|baki)\b"),
    ("payment_out", r"\b(paid to|payment to|paid supplier|chukaya|chukaye|diya supplier)\b"),
    ("bill", r"\b(bill from|purchase on credit|maal liya|bill aaya|invoice from)\b"),
    ("payment_in", r"\b(received|got|collected|payment from|jama kiya|paid me|paid us)\b.*\bfrom\b|\bne\b.*\b(diye|diya|di|bheje|bheja)\b|\bse\b.*\b(mila|mile|aaya|aaye)\b"),
    ("sale", r"\b(sold|sale|sales|becha|bechi|beche|bikri|bika|counter|galla)\b"),
    ("expense", r"\b(paid|spent|bought|purchase|kharcha|kharch|kharida|bill|fees|recharge)\b"),
]
STOP = {"to", "from", "for", "ko", "se", "ne", "the", "a", "an", "on", "of", "rs", "inr", "cash", "upi", "bank", "today", "yesterday", "aaj", "kal",
        "due", "paid", "sold", "sale", "received", "got", "payment", "udhaar", "udhar", "diye", "diya", "and", "worth", "bill", "credit",
        "becha", "bechi", "beche", "maal", "ka", "ki", "ke", "mila", "liya", "via", "in", "days", "lakh", "k", "goods", "items", "worth"}
DUE = re.compile(r"\bdue\s+(?:on\s+)?(\d{1,2})\s*([a-z]{3,9})\b|\bdue\s+in\s+(\d{1,3})\s*days?\b", re.I)


def _amount(text: str) -> tuple[float | None, tuple[int, int] | None]:
    best = None
    for m in AMOUNT.finditer(text):
        raw = m.group(1).replace(",", "")
        try:
            v = float(raw)
        except ValueError:
            continue
        unit = (m.group(2) or "").lower()
        # skip day numbers right after 'due'
        before = text[max(0, m.start() - 8): m.start()].lower()
        if "due" in before or re.match(r"\s*(days?|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", text[m.end(): m.end() + 5].lower()):
            continue
        v *= UNITS.get(unit, 1)
        if best is None or v > best[0]:
            best = (v, m.span())
    return (best[0], best[1]) if best else (None, None)


def _party(text: str, kind: str) -> str:
    t = re.sub(r"(?:₹|rs\.?)\s*\d[\d,.]*\s*(k|lakh|l)?", " ", text, flags=re.I)
    pats = [
        r"\b(?:to|from|for)\s+([A-Za-z][A-Za-z.&']*(?:\s+[A-Z][A-Za-z.&']*){0,3})",
        r"\b([A-Za-z][A-Za-z.&']*(?:\s+[A-Z][A-Za-z.&']*){0,2})\s+(?:ko|se|ne)\b",
    ]
    if kind in ("credit_sale", "payment_in"):
        pats = pats[::-1]
    for p in pats:
        for m in re.finditer(p, t):
            words = m.group(1).split()
            while words and (words[0].lower() in STOP or words[0].isdigit()):
                words = words[1:]
            words = [w for w in words if w.lower() not in STOP and not w.isdigit()]
            if words:
                name = " ".join(words)
                if name.lower() not in STOP and len(name) >= 2:
                    return name[:1].upper() + name[1:]
    return ""


def parse(text: str, today, known_parties: list[str] | None = None) -> dict:
    s = " ".join(str(text or "").split())
    low = s.lower()
    amount, _ = _amount(s)
    kind = None
    for k, pat in KIND_WORDS:
        if re.search(pat, low):
            kind = k
            break
    mode = next((v for k, v in MODES.items() if re.search(rf"\b{k}\b", low)), "cash")
    party = _party(s, kind or "sale")
    if known_parties and party:
        hit = next((p for p in known_parties if p.lower() == party.lower() or p.lower().startswith(party.lower() + " ")), None)
        party = hit or party
    if kind is None:
        kind = "expense" if any(re.search(rf"\b{w}\b", low) for w in ("rent", "salary", "bijli", "electricity", "petrol", "chai", "tea")) else "sale"
    date = pd.Timestamp(today).normalize()
    if re.search(r"\b(yesterday|kal)\b", low):
        date -= pd.Timedelta(days=1)
    due = None
    m = DUE.search(s)
    if m:
        if m.group(3):
            due = date + pd.Timedelta(days=int(m.group(3)))
        else:
            try:
                due = pd.Timestamp(f"{m.group(1)} {m.group(2)} {date.year}")
                if due < date:
                    due = due.replace(year=date.year + 1)
            except ValueError:
                due = None
    category = ""
    if kind in ("expense", "bill", "payment_out"):
        g = categorize(s, "out", party)
        category = g["category"] if g["confidence"] != "unknown" else ""
        if kind == "expense" and party and category and party.lower() in (category.lower(), "rent", "salary", "bijli"):
            party = ""
    missing = [f for f, v in (("amount", amount), ("party", party if kind in ("credit_sale", "payment_in", "bill", "payment_out") else "ok")) if not v]
    return {
        "kind": kind,
        "amount": amount,
        "party": party,
        "mode": mode,
        "category": category,
        "date": str(date.date()),
        "due_date": str(due.date()) if due is not None else None,
        "note": s[:200],
        "missing": missing,
    }
