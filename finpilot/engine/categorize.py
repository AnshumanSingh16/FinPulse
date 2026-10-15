"""
Auto-categorise bank statement lines.

Indian bank narrations look like 'UPI/RAVI KUMAR/ravi@okaxis/Payment', 'NEFT-HDFCN52-MSEDCL LTD' or
'ACH D- TP ACH ICICI BANK-LOAN EMI'. This module pulls out the other party's name and guesses a
category with plain keyword rules. The owner's own corrections ("always file X under Y") are
checked first. Every guess carries a confidence so uncertain ones can be shown for review — a
guess is never presented as certain.
"""

from __future__ import annotations

import re

# (keywords, category, direction or None) — checked in order; first match wins.
RULES: list[tuple[tuple[str, ...], str, str | None]] = [
    (("salary", "salaries", "wages", "payroll"), "Salaries", "out"),
    (("rent", "lease"), "Rent", "out"),
    (("msedcl", "bescom", "tneb", "tata power", "adani elec", "bses", "electricity", "power bill", "bijli", "torrent power", "cesc"), "Electricity", "out"),
    (("gst", "gstn", "cbic", "cgst", "sgst", "igst"), "GST Payment", "out"),
    (("tds", "income tax", "advance tax", "itns"), "TDS Payment", "out"),
    (("emi", "loan repay", "ach d", "nach"), "Loan EMI", "out"),
    (("loan disb", "loan credit", "disbursal"), "Loan Received", "in"),
    (("interest", "int.pd", "int pd", "sb int"), "Interest Received", "in"),
    (("refund", "reversal", "cashback"), "Refund Received", "in"),
    (("atm", "cash wdl", "cash withdrawal", "self"), "Transfer", None),
    (("charges", "chrg", "sms alert", "annual fee", "min bal", "gst on charges"), "Bank Charges", "out"),
    (("petrol", "diesel", "fuel", "hpcl", "iocl", "bpcl", "indian oil", "shell"), "Travel", "out"),
    (("ola", "uber", "rapido", "irctc", "makemytrip", "redbus"), "Travel", "out"),
    (("jio", "airtel", "vodafone", "vi ", "bsnl", "broadband", "act fibernet"), "Utilities", "out"),
    (("lic", "insurance", "policy", "acko", "hdfc ergo", "icici lombard"), "Insurance", "out"),
    (("zoho", "tally", "google", "microsoft", "aws", "razorpay sub", "software", "subscription"), "Software", "out"),
    (("facebook", "fb ads", "meta ads", "google ads", "justdial", "indiamart", "advert", "marketing"), "Marketing", "out"),
    (("delhivery", "bluedart", "dtdc", "vrl", "courier", "freight", "transport", "logistics", "porter", "shiprocket"), "Logistics", "out"),
    (("packag", "carton", "box", "pouch"), "Packaging", "out"),
    (("ca fees", "chartered", "consult", "legal", "advocate", "professional"), "Professional Fees", "out"),
    (("repair", "maintenance", "service charge"), "Repairs & Maintenance", "out"),
    (("stationery", "printing", "xerox"), "Office Supplies", "out"),
    (("swiggy", "zomato", "restaurant", "cafe", "chai", "tea", "snacks"), "Staff Welfare", "out"),
    (("amazon", "flipkart", "meesho", "udaan", "jiomart", "wholesale", "traders", "suppliers", "mandi", "kirana"), "Raw materials", "out"),
    (("drawing", "personal", "home exp"), "Owner Drawings", "out"),
]

PREFIX = re.compile(r"^(UPI|NEFT|IMPS|RTGS|ACH|NACH|BY TRANSFER|TO TRANSFER|TRF|INB|MMT|POS|CMS)[\s/:\-]*", re.I)
NOISE = re.compile(r"\b([A-Z]{4}0[A-Z0-9]{6}|\d{6,}|[\w.\-]+@[\w]+|[A-Z]{2,5}N\d{5,}|CR|DR|P2A|P2M|NA|PAYMENT|PAY|TO|FROM|BY|REF|TXN|UPI|NEFT|IMPS|RTGS)\b", re.I)


def extract_party(narration: str) -> str:
    """'UPI/RAVI KUMAR/ravi@okaxis/Payment' → 'Ravi Kumar'; 'NEFT-HDFCN52023-MSEDCL LTD-...' → 'Msedcl Ltd'."""
    s = str(narration or "").strip()
    if not s:
        return ""
    s = PREFIX.sub("", s)
    parts = [p.strip() for p in re.split(r"[/\-|:]+", s) if p.strip()]
    best = ""
    for p in parts:
        clean = NOISE.sub(" ", p)
        clean = re.sub(r"[^A-Za-z .&']", " ", clean)
        clean = re.sub(r"\s+", " ", clean).strip()
        if len(clean) >= 3 and sum(ch.isalpha() for ch in clean) >= 3:
            best = clean
            break
    return best.title() if best else ""


def categorize(narration: str, direction: str, party: str = "", learned: dict[str, str] | None = None) -> dict:
    """Return {'category', 'confidence': 'learned'|'high'|'guess'|'unknown', 'reason'}."""
    text = f" {narration} {party} ".lower()
    for match, cat in (learned or {}).items():
        if match and (match == (party or "").strip().lower() or f" {match} " in text or match in text):
            return {"category": cat, "confidence": "learned", "reason": f"You filed '{match}' under {cat}."}
    for words, cat, side in RULES:
        if side is not None and side != direction:
            continue
        for w in words:
            if (w in text) if " " in w or len(w) > 4 else re.search(rf"\b{re.escape(w)}\b", text):
                return {"category": cat, "confidence": "high", "reason": f"Contains '{w.strip()}'."}
    if direction == "in":
        return {"category": "Sales", "confidence": "guess", "reason": "Money received from a customer is assumed to be a sale. Check loans and transfers."}
    return {"category": "Uncategorised", "confidence": "unknown", "reason": "No rule matched."}


def categorize_ledger(ledger, learned: dict[str, str] | None = None, only_uncategorised: bool = True):
    """Fill party names and categories in a ledger DataFrame. Returns (ledger, counts)."""
    df = ledger.copy()
    counts = {"learned": 0, "high": 0, "guess": 0, "unknown": 0}
    for i, r in df.iterrows():
        party = r.get("counterparty") or ""
        if not party or party == "Unknown":
            party = extract_party(r.get("description", "")) or "Unknown"
            df.at[i, "counterparty"] = party
        if only_uncategorised and str(r.get("category", "")).strip() not in ("", "Uncategorised"):
            continue
        g = categorize(r.get("description", ""), r["direction"], party, learned)
        df.at[i, "category"] = g["category"]
        if g["confidence"] in ("guess", "unknown"):  # shown for review in the app
            df.at[i, "reference"] = (str(r.get("reference") or "") + " auto:guess").strip()
        counts[g["confidence"]] += 1
    return df, counts
