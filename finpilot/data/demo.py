"""
Deterministic demo data: a fictional Indian small business.

"Annapurna Masala Works", a spice processor in Pune (fictional — any resemblance is accidental),
twelve months from 1 Oct 2025 to 30 Sep 2026. The generator is seeded, and the output is also
committed under data/demo/, so the demo and the tests always see the same numbers.

Built-in situations for the demo to find:
  * raw-material costs up sharply in the last quarter
  * an electricity bill far above normal (Jul 2026)
  * a logistics payment recorded twice on the same day (Aug 2026)
  * a one-off consultancy fee (Sep 2026)
  * invoices from one customer overdue at the end of the period
  * a ₹5 lakh loan received and a ₹4.2 lakh machine bought with it — cash ≠ profit
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

AS_OF = date(2026, 9, 30)
START = date(2025, 10, 1)
OPENING_BALANCE = 6_20_000.0
ACCOUNT = "HDFC Current A/c"
BUSINESS = "Annapurna Masala Works (fictional)"
DEMO_DIR = Path(__file__).resolve().parents[2] / "data" / "demo"

CUSTOMERS = [
    "Shree Ganesh Traders",
    "Om Sai Distributors",
    "FreshMart Retail",
    "Patil Kirana Stores",
    "Metro Foods Pvt Ltd",
    "Kumar Wholesale",
]
SUPPLIERS = ["Kisan Agro Suppliers", "Rajasthan Spice Co", "Deccan Chillies"]


def _months(start: date, end: date):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def _day(y: int, m: int, d: int) -> date:
    for dd in range(d, 0, -1):
        try:
            return date(y, m, dd)
        except ValueError:
            continue
    raise ValueError("bad date")


def generate(seed: int = 7) -> dict[str, pd.DataFrame]:
    rng = random.Random(seed)
    ledger: list[dict] = []
    obligations: list[dict] = []

    def add(d, desc, cp, cat, direction, amount, mode="NEFT", ref=""):
        ledger.append(
            {
                "date": d,
                "description": desc,
                "counterparty": cp,
                "category": cat,
                "direction": direction,
                "amount": round(float(amount), 2),
                "payment_mode": mode,
                "reference": ref,
            }
        )

    inv_no = 0
    bill_no = 0
    month_index = 0

    # Invoices raised in September 2025, before the period starts, collected in October.
    for _ in range(9):
        inv_no += 1
        cust = rng.choice(CUSTOMERS)
        issued = date(2025, 9, rng.randint(1, 28))
        amount = round(rng.uniform(33_000, 1_00_000) / 100) * 100
        due = issued + timedelta(days=30)
        paid = max(due + timedelta(days=rng.choice([0, 2, 5])), START)
        obligations.append(
            {
                "item_id": f"INV-{inv_no:04d}",
                "kind": "receivable",
                "counterparty": cust,
                "description": f"Spice blends — invoice {inv_no:04d}",
                "category": "Sales - B2B",
                "amount": amount,
                "issue_date": issued,
                "due_date": due,
                "status": "paid",
                "paid_date": paid,
            }
        )
        add(paid, f"Receipt against INV-{inv_no:04d}", cust, "Sales - B2B", "in", amount, "NEFT", f"INV-{inv_no:04d}")
    for y, m in _months(START, AS_OF):
        growth = 1 + 0.015 * month_index
        late_qtr = (y, m) >= (2026, 7)

        # --- B2B invoices: 30-day terms, paid around the due date (some late, some pending)
        for _ in range(rng.randint(9, 11)):
            inv_no += 1
            cust = rng.choice(CUSTOMERS)
            issued = _day(y, m, rng.randint(1, 28))
            amount = round(rng.uniform(33_000, 1_00_000) * growth / 100) * 100
            due = issued + timedelta(days=30)
            delay = rng.choice([-3, 0, 0, 2, 5, 9, 14])
            paid = due + timedelta(days=delay)
            item = {
                "item_id": f"INV-{inv_no:04d}",
                "kind": "receivable",
                "counterparty": cust,
                "description": f"Spice blends — invoice {inv_no:04d}",
                "category": "Sales - B2B",
                "amount": amount,
                "issue_date": issued,
                "due_date": due,
                "status": "pending",
                "paid_date": None,
            }
            # Metro Foods stops paying from July 2026: those invoices go overdue.
            stuck = cust == "Metro Foods Pvt Ltd" and late_qtr
            if paid <= AS_OF and not stuck:
                item["status"] = "paid"
                item["paid_date"] = paid
                add(paid, f"Receipt against {item['item_id']}", cust, "Sales - B2B", "in", amount, "NEFT", item["item_id"])
            obligations.append(item)

        # --- Retail UPI collections, weekly
        for wk in range(4):
            d = _day(y, m, 6 + wk * 7)
            if d > AS_OF:
                break
            add(d, "UPI collections — factory outlet", "UPI settlement", "Sales - Retail", "in", round(rng.uniform(14_000, 26_000) * growth))

        # --- Raw material bills, 15-day terms
        for _ in range(rng.randint(4, 5)):
            bill_no += 1
            sup = rng.choice(SUPPLIERS)
            issued = _day(y, m, rng.randint(1, 26))
            base = rng.uniform(32_000, 52_000) * growth
            amount = round(base * (1.22 if late_qtr else 1.0) / 100) * 100
            due = issued + timedelta(days=15)
            item = {
                "item_id": f"BILL-{bill_no:04d}",
                "kind": "payable",
                "counterparty": sup,
                "description": "Whole spices and chillies",
                "category": "Raw materials",
                "amount": amount,
                "issue_date": issued,
                "due_date": due,
                "status": "pending",
                "paid_date": None,
            }
            if due <= AS_OF:
                item["status"] = "paid"
                item["paid_date"] = due
                add(due, f"Payment for {item['item_id']}", sup, "Raw materials", "out", amount, "NEFT", item["item_id"])
            obligations.append(item)

        # --- Fixed and recurring costs
        salaries = 1_85_000 if (y, m) < (2026, 4) else 2_05_000
        add(_day(y, m, 1), "Staff salaries (8)", "Staff payroll", "Salaries", "out", salaries, "NEFT")
        add(_day(y, m, 5), "Factory rent", "Hadapsar Industrial Estate", "Rent", "out", 55_000, "NEFT")
        elec = 61_400 if (y, m) == (2026, 7) else round(rng.uniform(18_000, 23_500))
        add(_day(y, m, 12), "Electricity bill", "MSEDCL", "Electricity", "out", elec, "Auto-debit")
        add(_day(y, m, 3), "Zoho Books subscription", "Zoho", "Software", "out", 2_950, "Card")
        add(_day(y, m, 18), "Packaging material", "PackWell Industries", "Packaging", "out", round(rng.uniform(21_000, 28_000) * growth), "NEFT")
        for wk in range(4):
            d = _day(y, m, 4 + wk * 7)
            amt = round(rng.uniform(8_500, 13_500) * growth)
            add(d, "Freight — dispatches", "VRL Logistics", "Logistics", "out", amt, "UPI")
            if (y, m) == (2026, 8) and wk == 2:
                # The same freight payment recorded twice.
                add(d, "Freight — dispatches", "VRL Logistics", "Logistics", "out", amt, "UPI")
        add(_day(y, m, 7), "Loan EMI", "HDFC Bank Business Loan", "Loan EMI", "out", 32_500, "Auto-debit")
        add(_day(y, m, 20), "GST payment", "GSTN", "GST Payment", "out", round(rng.uniform(26_000, 34_000) * growth), "Net banking")
        add(_day(y, m, 25), "Owner withdrawal", "Proprietor", "Owner Drawings", "out", 40_000, "Transfer")
        add(_day(y, m, 28), "Bank charges", "HDFC Bank", "Bank Charges", "out", round(rng.uniform(250, 600)), "Auto-debit")
        if m in (1, 4, 7, 10):
            add(_day(y, m, 15), "CA fees — quarterly", "Joshi & Associates", "Professional Fees", "out", 15_000, "NEFT")
        if m in (11, 2, 5, 8):
            add(_day(y, m, 10), "Trade fair stall / digital ads", "Spice India Expo", "Marketing", "out", round(rng.uniform(18_000, 30_000)), "Card")
        month_index += 1

    # One-offs
    add(date(2026, 1, 12), "Term loan disbursed", "HDFC Bank Business Loan", "Loan Received", "in", 5_00_000, "NEFT")
    add(date(2026, 2, 3), "Grinding machine (2 HP pulveriser)", "Laxmi Engineering Works", "Machinery", "out", 4_20_000, "RTGS")
    add(date(2026, 9, 22), "Consultancy — ISO 22000 certification", "QualiCert Advisors", "Professional Fees", "out", 95_000, "NEFT")

    led = pd.DataFrame(ledger).sort_values(["date", "description"], kind="stable").reset_index(drop=True)
    led.insert(0, "txn_id", [f"T{i + 1:04d}" for i in range(len(led))])

    # --- Scheduled outflows for the next 90 days (contractual or known): what a forecast can use.
    sched = []
    for y, m in _months(date(2026, 10, 1), date(2026, 12, 31)):
        for desc, cp, cat, d, amt in [
            ("Staff salaries (8)", "Staff payroll", "Salaries", 1, 2_05_000),
            ("Factory rent", "Hadapsar Industrial Estate", "Rent", 5, 55_000),
            ("Loan EMI", "HDFC Bank Business Loan", "Loan EMI", 7, 32_500),
            ("Zoho Books subscription", "Zoho", "Software", 3, 2_950),
        ]:
            bill_no += 1
            sched.append(
                {
                    "item_id": f"SCH-{bill_no:04d}",
                    "kind": "payable",
                    "counterparty": cp,
                    "description": desc,
                    "category": cat,
                    "amount": float(amt),
                    "issue_date": None,
                    "due_date": _day(y, m, d),
                    "status": "pending",
                    "paid_date": None,
                }
            )
    # An overdue payable: September's electricity was paid, but a packaging bill is unpaid and late.
    sched.append(
        {
            "item_id": "BILL-PKG-0926",
            "kind": "payable",
            "counterparty": "PackWell Industries",
            "description": "Pouches and cartons — September",
            "category": "Packaging",
            "amount": 26_800.0,
            "issue_date": date(2026, 9, 5),
            "due_date": date(2026, 9, 25),
            "status": "pending",
            "paid_date": None,
        }
    )
    obl = pd.DataFrame(obligations + sched)

    # --- Balances: opening, plus a reconciling statement balance mid-year.
    def balance_on(d: date) -> float:
        rows = led[led["date"] <= d]
        signed = rows.apply(lambda r: r["amount"] if r["direction"] == "in" else -r["amount"], axis=1)
        return round(OPENING_BALANCE + float(signed.sum()), 2)

    bal = pd.DataFrame(
        [
            {"as_of": START - timedelta(days=1), "account": ACCOUNT, "balance": OPENING_BALANCE},
            {"as_of": date(2026, 6, 30), "account": ACCOUNT, "balance": balance_on(date(2026, 6, 30))},
        ]
    )
    for df, cols in ((led, ["date"]), (obl, ["issue_date", "due_date", "paid_date"]), (bal, ["as_of"])):
        for c in cols:
            df[c] = pd.to_datetime(df[c])
    return {"ledger": led, "obligations": obl, "balances": bal}


def write_demo_files(out: Path = DEMO_DIR) -> None:
    out.mkdir(parents=True, exist_ok=True)
    data = generate()
    for name, df in data.items():
        df.to_csv(out / f"{name}.csv", index=False, date_format="%Y-%m-%d")


def load_demo() -> dict[str, pd.DataFrame]:
    """The committed demo files, parsed. Falls back to generating them if missing."""
    if not (DEMO_DIR / "ledger.csv").exists():
        write_demo_files()
    led = pd.read_csv(DEMO_DIR / "ledger.csv", parse_dates=["date"], dtype={"reference": str})
    obl = pd.read_csv(DEMO_DIR / "obligations.csv", parse_dates=["issue_date", "due_date", "paid_date"])
    bal = pd.read_csv(DEMO_DIR / "balances.csv", parse_dates=["as_of"])
    led["reference"] = led["reference"].fillna("")
    return {"ledger": led, "obligations": obl, "balances": bal}


if __name__ == "__main__":
    write_demo_files()
    print(f"Wrote demo data to {DEMO_DIR}")
