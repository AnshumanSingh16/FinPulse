"""
Uploads: read CSV/XLSX, suggest a column mapping, then parse and validate into the canonical tables.

Nothing is silently changed: every rejected row gets a reason, every filled-in value is counted,
and possible duplicates are reported (kept unless the user chooses to drop exact copies).
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from finpilot.engine.expenses import find_duplicates

SYNONYMS: dict[str, list[str]] = {
    "date": ["date", "txn date", "transaction date", "value date", "posting date", "voucher date", "tran date"],
    "description": ["description", "narration", "particulars", "details", "remarks", "memo", "transaction details"],
    "counterparty": ["counterparty", "party", "vendor", "customer", "payee", "payer", "name", "beneficiary", "ledger name"],
    "category": ["category", "head", "account head", "expense head", "ledger", "group", "type of expense"],
    "amount": ["amount", "amount (inr)", "amount inr", "value", "txn amount", "transaction amount", "amt"],
    "debit": ["debit", "withdrawal", "withdrawals", "dr", "debit amount", "paid out", "money out"],
    "credit": ["credit", "deposit", "deposits", "cr", "credit amount", "paid in", "money in"],
    "direction": ["direction", "dr/cr", "cr/dr", "type", "transaction type", "in/out"],
    "payment_mode": ["payment mode", "mode", "channel", "instrument"],
    "reference": ["reference", "ref", "ref no", "cheque no", "utr", "invoice no", "chq/ref no"],
    "currency": ["currency", "ccy", "curr"],
    # obligations
    "kind": ["kind", "receivable/payable", "invoice type", "doc type"],
    "item_id": ["item_id", "invoice no", "bill no", "invoice number", "bill number", "document no", "id"],
    "issue_date": ["issue date", "invoice date", "bill date", "issued"],
    "due_date": ["due date", "due", "payment due", "due on"],
    "status": ["status", "payment status", "paid?"],
    "paid_date": ["paid date", "payment date", "date paid", "settled on"],
    # balances
    "as_of": ["as of", "as_of", "balance date", "statement date", "date"],
    "account": ["account", "account name", "bank account", "bank"],
    "balance": ["balance", "closing balance", "opening balance", "available balance"],
}

TABLE_FIELDS = {
    "ledger": ["date", "description", "counterparty", "category", "amount", "debit", "credit", "direction", "payment_mode", "reference", "currency"],
    "obligations": ["item_id", "kind", "counterparty", "description", "category", "amount", "issue_date", "due_date", "status", "paid_date", "currency"],
    "balances": ["as_of", "account", "balance"],
}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9/]+", " ", str(s).lower()).strip()


def read_table(data: bytes, filename: str, sheet: str | int | None = 0) -> pd.DataFrame:
    """Read an uploaded CSV or XLSX into strings (parsing happens later, with reasons)."""
    name = filename.lower()
    if name.endswith((".xlsx", ".xlsm")):
        return pd.read_excel(io.BytesIO(data), sheet_name=sheet, dtype=object, engine="openpyxl")
    if name.endswith(".csv") or name.endswith(".txt"):
        for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
            try:
                return pd.read_csv(io.BytesIO(data), dtype=str, encoding=enc, keep_default_na=False)
            except UnicodeDecodeError:
                continue
    raise ValueError("Upload a .csv or .xlsx file.")


def excel_sheets(data: bytes) -> list[str]:
    return pd.ExcelFile(io.BytesIO(data), engine="openpyxl").sheet_names


def suggest_mapping(columns: list[str], table: str) -> dict[str, str | None]:
    """Best-guess source column for each canonical field (None if nothing matches)."""
    norm = {c: _norm(c) for c in columns}
    used: set[str] = set()
    out: dict[str, str | None] = {}
    for f in TABLE_FIELDS[table]:
        choice = None
        for syn in map(_norm, SYNONYMS.get(f, [f])):
            for c, n in norm.items():
                if c not in used and n == syn:
                    choice = c
                    break
            if choice:
                break
        if choice is None:
            for syn in map(_norm, SYNONYMS.get(f, [f])):
                for c, n in norm.items():
                    if c not in used and len(syn) > 3 and syn in n:
                        choice = c
                        break
                if choice:
                    break
        out[f] = choice
        if choice:
            used.add(choice)
    return out


# ---------------------------------------------------------------- parsing

# "cr" is deliberately not a unit: after an amount it is the bank-statement credit marker.
_UNITS = {"lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "lacs": 1e5, "l": 1e5, "crore": 1e7, "crores": 1e7, "k": 1e3}


def parse_amount(value) -> tuple[float | None, str | None]:
    """
    Parse an Indian-format amount. Returns (amount, direction hint).
    Handles ₹/Rs./INR, Indian or western grouping, (1,234) and trailing '-' as negative,
    'Dr'/'Cr' suffixes (debit/credit, as on bank statements) and '2.5 lakh' / '1.2 crore'. Blank, '-' and junk return (None, None).
    """
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None, None
    if isinstance(value, (int, float, np.integer, np.floating)):
        return float(value), None
    s = str(value).strip()
    if s in ("", "-", "—", "nan", "NaN", "None"):
        return None, None
    hint = None
    low = s.lower()
    m = re.search(r"\b(dr|cr)\.?$", low)
    if m:
        hint = "out" if m.group(1) == "dr" else "in"
        low = low[: m.start()].strip()
    neg = False
    if low.startswith("(") and low.endswith(")"):
        neg, low = True, low[1:-1]
    low = re.sub(r"(₹|rs\.?|inr)", "", low).strip()
    if low.endswith("-"):
        neg, low = True, low[:-1].strip()
    if low.startswith("-"):
        neg, low = True, low[1:].strip()
    if low.startswith("+"):
        low = low[1:].strip()
    mult = 1.0
    mu = re.match(r"^([\d.,]+)\s*([a-z]+)$", low)
    if mu and mu.group(2) in _UNITS:
        low, mult = mu.group(1), _UNITS[mu.group(2)]
    low = low.replace(",", "").replace(" ", "")
    if not re.fullmatch(r"\d+(\.\d+)?|\.\d+", low):
        return None, None
    v = float(low) * mult
    return (-v if neg else v), hint


def parse_date(value) -> pd.Timestamp | None:
    """Day-first dates (Indian convention), ISO dates and Excel serial numbers."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    if isinstance(value, pd.Timestamp):
        return value.normalize()
    if hasattr(value, "year") and hasattr(value, "month"):
        return pd.Timestamp(value).normalize()
    s = str(value).strip()
    if not s or s.lower() in ("nan", "nat", "none", "-"):
        return None
    if re.fullmatch(r"\d{5}(\.\d+)?", s):  # Excel serial
        return (pd.Timestamp("1899-12-30") + pd.Timedelta(days=float(s))).normalize()
    iso = re.fullmatch(r"\d{4}-\d{2}-\d{2}([ T].*)?", s)
    try:
        d = pd.to_datetime(s, dayfirst=not iso, errors="raise")
    except (ValueError, TypeError, OverflowError):
        return None
    if d.year < 1990 or d.year > 2100:
        return None
    return d.normalize()


# ---------------------------------------------------------------- building tables


@dataclass
class ValidationReport:
    table: str
    rows_in: int = 0
    rows_ok: int = 0
    rejected: list[dict] = field(default_factory=list)  # {"row": n, "reason": str}
    warnings: list[str] = field(default_factory=list)
    filled: dict[str, int] = field(default_factory=dict)
    duplicate_groups: list[list[str]] = field(default_factory=list)
    exact_duplicates_dropped: int = 0

    @property
    def ok(self) -> bool:
        return self.rows_ok > 0

    def to_dict(self) -> dict:
        return {
            "table": self.table,
            "rows_in": self.rows_in,
            "rows_ok": self.rows_ok,
            "rejected": self.rejected,
            "warnings": self.warnings,
            "filled": self.filled,
            "duplicate_groups": self.duplicate_groups,
            "exact_duplicates_dropped": self.exact_duplicates_dropped,
        }


def _col(raw: pd.DataFrame, mapping: dict, key: str):
    src = mapping.get(key)
    return raw[src] if src and src in raw.columns else None


def _direction_word(v) -> str | None:
    s = _norm(v)
    if s in ("in", "credit", "cr", "receipt", "deposit", "income", "inflow", "received", "c"):
        return "in"
    if s in ("out", "debit", "dr", "payment", "withdrawal", "expense", "outflow", "paid", "d"):
        return "out"
    return None


def _check_currency(raw, mapping, report, keep) -> list[bool]:
    cur = _col(raw, mapping, "currency")
    if cur is None:
        return keep
    for i, c in enumerate(cur):
        if keep[i] and str(c).strip() and str(c).strip().upper() not in ("INR", "₹", "RS", "RS."):
            keep[i] = False
            report.rejected.append({"row": i + 2, "reason": f"Currency {c} is not INR — FinPilot does not convert currencies."})
    return keep


def build_ledger(raw: pd.DataFrame, mapping: dict, drop_exact_duplicates: bool = False) -> tuple[pd.DataFrame, ValidationReport]:
    """
    Parse a raw ledger / bank statement. Amounts can come as:
      * one signed amount column (negative = outflow), or
      * an amount column plus a direction column (Dr/Cr, in/out…), or
      * separate debit and credit columns.
    """
    rep = ValidationReport("ledger", rows_in=len(raw))
    n = len(raw)
    keep = [True] * n
    keep = _check_currency(raw, mapping, rep, keep)
    dates, amounts, dirs = [None] * n, [None] * n, [None] * n

    dcol = _col(raw, mapping, "date")
    if dcol is None:
        rep.warnings.append("No date column mapped — every row needs a date.")
        return pd.DataFrame(columns=["txn_id"]), rep
    amt, deb, cred, dircol = (_col(raw, mapping, k) for k in ("amount", "debit", "credit", "direction"))
    if amt is None and deb is None and cred is None:
        rep.warnings.append("No amount column mapped (map 'amount', or 'debit' and 'credit').")
        return pd.DataFrame(columns=["txn_id"]), rep

    for i in range(n):
        if not keep[i]:
            continue
        d = parse_date(dcol.iloc[i])
        if d is None:
            keep[i] = False
            rep.rejected.append({"row": i + 2, "reason": f"Unreadable or missing date: '{dcol.iloc[i]}'"})
            continue
        dates[i] = d
        value, direction = None, None
        if deb is not None or cred is not None:
            dv, _ = parse_amount(deb.iloc[i]) if deb is not None else (None, None)
            cv, _ = parse_amount(cred.iloc[i]) if cred is not None else (None, None)
            dv, cv = abs(dv or 0.0), abs(cv or 0.0)
            if dv and cv:
                keep[i] = False
                rep.rejected.append({"row": i + 2, "reason": "Both debit and credit filled in on one row."})
                continue
            if dv:
                value, direction = dv, "out"
            elif cv:
                value, direction = cv, "in"
        if value is None and amt is not None:
            v, hint = parse_amount(amt.iloc[i])
            if v is not None:
                word = _direction_word(dircol.iloc[i]) if dircol is not None else None
                direction = word or hint or ("out" if v < 0 else "in")
                if dircol is not None and word is None and hint is None and v >= 0:
                    rep.filled["direction_from_sign"] = rep.filled.get("direction_from_sign", 0) + 1
                value = abs(v)
        if value is None:
            keep[i] = False
            rep.rejected.append({"row": i + 2, "reason": "Missing or unreadable amount."})
            continue
        if value == 0:
            keep[i] = False
            rep.rejected.append({"row": i + 2, "reason": "Amount is zero."})
            continue
        amounts[i], dirs[i] = round(value, 2), direction

    def text(key, default, label):
        col = _col(raw, mapping, key)
        vals = []
        for i in range(n):
            v = "" if col is None else str(col.iloc[i]).strip()
            if v in ("", "nan", "None") and keep[i]:
                rep.filled[label] = rep.filled.get(label, 0) + 1
                v = default
            vals.append(v)
        return vals

    out = pd.DataFrame(
        {
            "date": dates,
            "description": text("description", "(no description)", "description"),
            "counterparty": text("counterparty", "Unknown", "counterparty"),
            "category": text("category", "Uncategorised", "category"),
            "direction": dirs,
            "amount": amounts,
            "payment_mode": text("payment_mode", "", "payment_mode_blank"),
            "reference": text("reference", "", "reference_blank"),
            "source_row": [i + 2 for i in range(n)],
        }
    )[keep]
    rep.filled.pop("payment_mode_blank", None)
    rep.filled.pop("reference_blank", None)
    out = out.sort_values(["date", "source_row"], kind="stable").reset_index(drop=True)
    out.insert(0, "txn_id", [f"U{i + 1:05d}" for i in range(len(out))])
    out["date"] = pd.to_datetime(out["date"])

    if rep.filled.get("category"):
        rep.warnings.append(
            f"{rep.filled['category']} row(s) had no category and were set to 'Uncategorised' "
            "(outflows count as operating expenses; inflows are not counted as revenue)."
        )
    exact = out.duplicated(subset=["date", "description", "counterparty", "category", "direction", "amount", "reference"], keep="first")
    if drop_exact_duplicates and exact.any():
        rep.exact_duplicates_dropped = int(exact.sum())
        out = out[~exact].reset_index(drop=True)
    rep.duplicate_groups = find_duplicates(out)
    if rep.duplicate_groups:
        rep.warnings.append(
            f"{len(rep.duplicate_groups)} group(s) of possible duplicates (same date, amount, party, category). "
            "They are kept — check whether each is a genuine repeat payment."
        )
    if rep.exact_duplicates_dropped:
        rep.warnings.append(f"Dropped {rep.exact_duplicates_dropped} exact duplicate row(s) at your request.")
    rep.rows_ok = len(out)
    return out, rep


def build_obligations(raw: pd.DataFrame, mapping: dict) -> tuple[pd.DataFrame, ValidationReport]:
    rep = ValidationReport("obligations", rows_in=len(raw))
    rows = []
    for i in range(len(raw)):
        get = lambda k: (_col(raw, mapping, k).iloc[i] if _col(raw, mapping, k) is not None else None)  # noqa: E731
        cur = get("currency")
        if cur is not None and str(cur).strip() and str(cur).strip().upper() not in ("INR", "₹", "RS", "RS."):
            rep.rejected.append({"row": i + 2, "reason": f"Currency {cur} is not INR."})
            continue
        kind_raw = _norm(get("kind") or "")
        kind = "receivable" if kind_raw.startswith(("rec", "inv", "sale", "ar")) else "payable" if kind_raw.startswith(("pay", "bill", "purch", "ap")) else None
        amount, _ = parse_amount(get("amount"))
        due = parse_date(get("due_date"))
        status_raw = _norm(get("status") or "")
        status = "paid" if status_raw in ("paid", "settled", "closed", "yes", "received", "done") else "pending" if status_raw in ("pending", "unpaid", "open", "due", "overdue", "no", "outstanding", "partly paid") else None
        reasons = []
        if kind is None:
            reasons.append(f"type '{get('kind')}' is not receivable/payable")
        if amount is None or amount <= 0:
            reasons.append("missing or invalid amount")
        if due is None:
            reasons.append("missing or unreadable due date")
        if status is None:
            reasons.append(f"status '{get('status')}' is not paid/pending")
        if reasons:
            rep.rejected.append({"row": i + 2, "reason": "; ".join(reasons)})
            continue
        if status_raw == "partly paid":
            rep.warnings.append(f"Row {i + 2} is partly paid; the full amount is treated as pending.")
        rows.append(
            {
                "item_id": str(get("item_id") or f"OBL-{i + 2}").strip(),
                "kind": kind,
                "counterparty": str(get("counterparty") or "Unknown").strip(),
                "description": str(get("description") or "").strip(),
                "category": str(get("category") or ("Sales" if kind == "receivable" else "Uncategorised")).strip(),
                "amount": round(abs(amount), 2),
                "issue_date": parse_date(get("issue_date")),
                "due_date": due,
                "status": status,
                "paid_date": parse_date(get("paid_date")),
            }
        )
    out = pd.DataFrame(rows, columns=["item_id", "kind", "counterparty", "description", "category", "amount", "issue_date", "due_date", "status", "paid_date"])
    for c in ("issue_date", "due_date", "paid_date"):
        out[c] = pd.to_datetime(out[c])
    dup_ids = out["item_id"][out["item_id"].duplicated(keep=False)].unique().tolist()
    if dup_ids:
        rep.warnings.append(f"Repeated invoice/bill numbers: {', '.join(map(str, dup_ids[:10]))}. Check for double entries.")
        rep.duplicate_groups = [[i] for i in dup_ids]
    rep.rows_ok = len(out)
    return out, rep


def build_balances(raw: pd.DataFrame, mapping: dict) -> tuple[pd.DataFrame, ValidationReport]:
    rep = ValidationReport("balances", rows_in=len(raw))
    rows = []
    for i in range(len(raw)):
        get = lambda k: (_col(raw, mapping, k).iloc[i] if _col(raw, mapping, k) is not None else None)  # noqa: E731
        d = parse_date(get("as_of"))
        b, _ = parse_amount(get("balance"))
        if d is None or b is None:
            rep.rejected.append({"row": i + 2, "reason": "A balance needs a readable date and amount."})
            continue
        rows.append({"as_of": d, "account": str(get("account") or "Main account").strip(), "balance": round(b, 2)})
    out = pd.DataFrame(rows, columns=["as_of", "account", "balance"])
    out["as_of"] = pd.to_datetime(out["as_of"])
    if out["account"].nunique() > 1:
        rep.warnings.append("Several accounts found; the cash position uses all balances as one pool only if the ledger covers every account.")
    rep.rows_ok = len(out)
    return out, rep
