"""
More demo businesses, each with a cash crunch coming for the autopilot to find and fix.

Every business is generated deterministically (seeded) from a small profile: who pays it (invoiced clients
and/or daily sales), who it pays (supplier bills, fixed costs), one-offs, and the known payments ahead.
All names are fictional. The original manufacturer demo stays in finpilot.data.demo.

  agency  Pixel Pundit Studio — a 12-person design and digital agency in Bengaluru (services).
          A hospital client stopped paying in July; an office deposit, salaries and an annual software renewal
          land in late Oct / 1 Nov.
  cafe    Brew & Bun Café — a busy café in Mumbai (restaurant).
          A corporate catering client is late; the Diwali stock-up, a kitchen fit-out advance and the 1 Dec rent
          and salaries collide.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

from finpilot.data.demo import AS_OF, START, _day, _months


@dataclass
class Client:
    name: str
    monthly: float  # retainer / regular invoice
    terms: int
    delays: list[int]
    stuck_from: tuple[int, int] | None = None  # (year, month) from which invoices go unpaid
    desc: str = "Monthly retainer"
    category: str = "Service Income"


@dataclass
class Supplier:
    name: str
    desc: str
    category: str
    per_month: tuple[int, int]
    amount: tuple[float, float]
    terms: int


@dataclass
class Profile:
    key: str
    business: str
    kind: str  # business type
    city: str
    opening: float
    clients: list[Client]
    suppliers: list[Supplier]
    fixed: list[tuple[str, str, str, int, float, str]]  # desc, counterparty, category, day, amount, mode
    variable: list[tuple[str, str, str, int, tuple[float, float], str]]
    daily_sales: tuple[str, str, float, float] | None = None  # desc, counterparty, weekday amount, weekend amount
    weekly_payout: tuple[str, float, float, int] | None = None  # aggregator name, low, high, terms (as receivables)
    projects: tuple[float, float, float] | None = None  # chance per month, low, high
    one_offs: list[tuple[date, str, str, str, str, float]] = field(default_factory=list)
    ahead: list[tuple[date, str, str, str, float]] = field(default_factory=list)  # known future bills: due, desc, cp, category, amount
    scheduled_fixed: tuple[str, ...] = ("Salaries", "Rent", "Loan EMI", "Software")


AGENCY = Profile(
    key="agency",
    business="Pixel Pundit Studio (fictional)",
    kind="services",
    city="Bengaluru",
    opening=10_50_000,
    clients=[
        Client("Zenith Realty", 2_10_000, 30, [0, 3, 7, 12]),
        Client("Bloom Organics", 1_20_000, 30, [0, 0, 2]),
        Client("UrbanFit Gyms", 1_40_000, 30, [5, 10, 15]),
        Client("Kaveri Hospitals", 2_40_000, 30, [0, 4], stuck_from=(2026, 7)),
        Client("Nimbus EdTech", 1_70_000, 30, [0, 2, 3]),
    ],
    suppliers=[
        Supplier("Arjun Rao (freelance motion designer)", "Freelance animation work", "Professional Fees", (1, 2), (28_000, 55_000), 15),
        Supplier("ClickStream Media", "Paid ads managed for clients", "Marketing", (1, 1), (40_000, 70_000), 21),
        Supplier("Studio Lens Photography", "Product shoot", "Professional Fees", (0, 1), (35_000, 60_000), 15),
    ],
    fixed=[
        ("Team salaries (12)", "Staff payroll", "Salaries", 1, 4_20_000, "NEFT"),
        ("Office rent — Indiranagar", "Sunrise Properties", "Rent", 5, 95_000, "NEFT"),
        ("Design software seats", "Adobe & Figma", "Software", 3, 32_000, "Card"),
        ("Internet and phones", "ACT Fibernet", "Utilities", 10, 9_500, "Auto-debit"),
        ("Owner withdrawal", "Proprietor", "Owner Drawings", 28, 75_000, "Transfer"),
    ],
    variable=[
        ("GST payment", "GSTN", "GST Payment", 20, (1_05_000, 1_25_000), "Net banking"),
        ("Team lunches and coffee", "Third Wave Cafe", "Staff Welfare", 15, (9_000, 16_000), "UPI"),
        ("Bank charges", "ICICI Bank", "Bank Charges", 28, (300, 700), "Auto-debit"),
    ],
    projects=(0.55, 60_000, 2_40_000),
    one_offs=[
        (date(2026, 3, 18), "MacBook Pro x3 for designers", "Croma Business", "Equipment", "out", 6_30_000),
        (date(2026, 9, 15), "Advance tax — 2nd instalment", "Income Tax Dept", "Income Tax", "out", 1_40_000),
        (date(2025, 12, 15), "Advance tax — 3rd instalment", "Income Tax Dept", "Income Tax", "out", 1_20_000),
    ],
    ahead=[
        (date(2026, 10, 25), "Deposit for the new office floor", "Sunrise Properties", "Rent", 3_50_000),
        (date(2026, 11, 1), "Annual software renewal (Adobe team plan)", "Adobe & Figma", "Software", 2_60_000),
        (date(2026, 12, 15), "Advance tax — 3rd instalment", "Income Tax Dept", "Income Tax", 1_40_000),
        (date(2026, 10, 20), "GST for September", "GSTN", "GST Payment", 1_18_000),
        (date(2026, 11, 20), "GST for October", "GSTN", "GST Payment", 1_10_000),
    ],
)

CAFE = Profile(
    key="cafe",
    business="Brew & Bun Café (fictional)",
    kind="restaurant",
    city="Mumbai",
    opening=11_40_000,
    clients=[
        Client("Techno Park Pvt Ltd", 92_000, 30, [0, 5], stuck_from=(2026, 8), desc="Office catering — monthly", category="Sales - B2B"),
        Client("Seaview Co-working", 38_000, 15, [0, 2, 6], desc="Coffee service — monthly", category="Sales - B2B"),
    ],
    suppliers=[
        Supplier("Fresh Dairy Co", "Milk, cream and paneer", "Purchases", (4, 4), (34_000, 44_000), 7),
        Supplier("Bombay Bakery Supplies", "Breads, buns and pastry base", "Purchases", (4, 4), (19_000, 27_000), 7),
        Supplier("Green Basket Vegetables", "Vegetables and fruit", "Purchases", (4, 4), (14_000, 21_000), 7),
        Supplier("Coffee Estate Roasters", "Coffee beans — monthly", "Raw materials", (1, 1), (88_000, 1_08_000), 15),
    ],
    fixed=[
        ("Shop rent — Bandra", "Hill Road Estates", "Rent", 1, 3_10_000, "NEFT"),
        ("Staff salaries (14)", "Staff payroll", "Salaries", 1, 4_40_000, "NEFT"),
        ("Espresso machine loan EMI", "Bajaj Finance", "Loan EMI", 7, 42_000, "Auto-debit"),
        ("POS and billing software", "Petpooja-style POS", "Software", 3, 4_500, "Card"),
        ("Owner withdrawal", "Proprietor", "Owner Drawings", 26, 70_000, "Transfer"),
    ],
    variable=[
        ("Electricity bill", "Adani Electricity", "Electricity", 12, (58_000, 74_000), "Auto-debit"),
        ("Cooking gas cylinders", "Mahanagar Gas", "Fuel", 9, (16_000, 21_000), "UPI"),
        ("Instagram ads and flyers", "Meta Ads", "Marketing", 14, (18_000, 34_000), "Card"),
        ("GST payment", "GSTN", "GST Payment", 20, (48_000, 58_000), "Net banking"),
        ("Repairs — coffee machine and AC", "CoolTech Services", "Repairs & Maintenance", 22, (6_000, 22_000), "UPI"),
        ("Bank charges", "HDFC Bank", "Bank Charges", 28, (900, 1_600), "Auto-debit"),
    ],
    daily_sales=("Card and UPI settlement", "Counter sales (POS)", 31_000, 46_000),
    weekly_payout=("Zippy Eats (delivery app)", 52_000, 74_000, 7),
    ahead=[
        (date(2026, 10, 18), "Diwali stock-up — sweets, dry fruit, gift hampers", "Mithai Wholesale Mart", "Purchases", 2_45_000),
        (date(2026, 11, 2), "Annual FSSAI and trade licence renewal", "BMC Licensing", "Professional Fees", 85_000),
        (date(2026, 11, 25), "Kitchen exhaust and fit-out upgrade — advance", "Pro Kitchen Fitouts", "Repairs & Maintenance", 2_60_000),
        (date(2026, 10, 20), "GST for September", "GSTN", "GST Payment", 56_000),
    ],
)

PROFILES = {p.key: p for p in (AGENCY, CAFE)}


def generate(profile: Profile, seed: int = 11) -> dict[str, pd.DataFrame]:
    rng = random.Random(f"{profile.key}:{seed}")
    ledger: list[dict] = []
    obligations: list[dict] = []
    n_inv = n_bill = 0

    def add(d, desc, cp, cat, direction, amount, mode="NEFT", ref=""):
        ledger.append({"date": d, "description": desc, "counterparty": cp, "category": cat, "direction": direction,
                       "amount": round(float(amount), 2), "payment_mode": mode, "reference": ref})

    def receivable(cp, desc, cat, amount, issued, terms, delay, stuck):
        nonlocal n_inv
        n_inv += 1
        iid = f"INV-{n_inv:04d}"
        due = issued + timedelta(days=terms)
        paid = due + timedelta(days=delay)
        item = {"item_id": iid, "kind": "receivable", "counterparty": cp, "description": desc, "category": cat, "amount": round(amount, -2) or amount,
                "issue_date": issued, "due_date": due, "status": "pending", "paid_date": None}
        if paid <= AS_OF and not stuck:
            item.update(status="paid", paid_date=max(paid, START))
            add(item["paid_date"], f"Receipt against {iid}", cp, cat, "in", item["amount"], "NEFT", iid)
        obligations.append(item)

    def payable(cp, desc, cat, amount, issued, terms, unpaid=False):
        nonlocal n_bill
        n_bill += 1
        bid = f"BILL-{n_bill:04d}"
        due = issued + timedelta(days=terms)
        item = {"item_id": bid, "kind": "payable", "counterparty": cp, "description": desc, "category": cat, "amount": round(amount, -2) or amount,
                "issue_date": issued, "due_date": due, "status": "pending", "paid_date": None}
        if due <= AS_OF and not unpaid:
            item.update(status="paid", paid_date=max(due, START))
            add(item["paid_date"], f"Payment for {bid}", cp, cat, "out", item["amount"], "NEFT", bid)
        obligations.append(item)

    months = list(_months(START, AS_OF))
    for idx, (y, m) in enumerate(months):
        growth = 1 + 0.01 * idx
        for c in profile.clients:
            stuck = c.stuck_from is not None and (y, m) >= c.stuck_from
            receivable(c.name, f"{c.desc} — {date(y, m, 1):%b %Y}", c.category, c.monthly * growth, _day(y, m, 1), c.terms, rng.choice(c.delays), stuck)
        if profile.projects and rng.random() < profile.projects[0]:
            c = rng.choice([c for c in profile.clients if c.stuck_from is None])
            receivable(c.name, "Project — campaign / website", c.category, rng.uniform(*profile.projects[1:]), _day(y, m, rng.randint(8, 24)), c.terms, rng.choice(c.delays), False)
        for s in profile.suppliers:
            for _ in range(rng.randint(*s.per_month)):
                payable(s.name, s.desc, s.category, rng.uniform(*s.amount) * growth, _day(y, m, rng.randint(1, 26)), s.terms)
        for desc, cp, cat, d, amount, mode in profile.fixed:
            add(_day(y, m, d), desc, cp, cat, "out", amount, mode)
        for desc, cp, cat, d, rng_amt, mode in profile.variable:
            add(_day(y, m, d), desc, cp, cat, "out", round(rng.uniform(*rng_amt) * growth), mode)
        if profile.daily_sales:
            desc, cp, wk, we = profile.daily_sales
            day = date(y, m, 1)
            while day.month == m and day <= AS_OF:
                base = we if day.weekday() >= 5 else wk
                add(day, desc, cp, "Sales - Retail", "in", round(base * rng.uniform(0.85, 1.15) * growth), "UPI")
                day += timedelta(days=1)
        if profile.weekly_payout:
            name, lo, hi, terms = profile.weekly_payout
            for wk in range(4):
                issued = _day(y, m, 1 + wk * 7)
                receivable(name, f"Delivery orders — week of {issued:%d %b}", "Sales - Retail", rng.uniform(lo, hi) * growth, issued, terms, rng.choice([0, 1, 2]), False)
    for d, desc, cp, cat, direction, amount in profile.one_offs:
        add(d, desc, cp, cat, direction, amount, "NEFT")

    led = pd.DataFrame(ledger).sort_values(["date", "description"], kind="stable").reset_index(drop=True)
    led.insert(0, "txn_id", [f"T{i + 1:04d}" for i in range(len(led))])

    # --- What is already known about the next 90 days.
    ahead = []
    for y, m in _months(date(2026, 10, 1), date(2026, 12, 31)):
        for desc, cp, cat, d, amount, _mode in profile.fixed:
            if cat in profile.scheduled_fixed:
                ahead.append((_day(y, m, d), desc, cp, cat, amount))
    ahead += [(d, desc, cp, cat, amt) for d, desc, cp, cat, amt in profile.ahead]
    for i, (due, desc, cp, cat, amount) in enumerate(sorted(ahead, key=lambda x: x[0]), 1):
        obligations.append({"item_id": f"SCH-{i:04d}", "kind": "payable", "counterparty": cp, "description": desc, "category": cat, "amount": float(amount),
                            "issue_date": None, "due_date": due, "status": "pending", "paid_date": None})
    obl = pd.DataFrame(obligations)

    def balance_on(d: date) -> float:
        rows = led[led["date"] <= d]
        signed = rows.apply(lambda r: r["amount"] if r["direction"] == "in" else -r["amount"], axis=1)
        return round(profile.opening + float(signed.sum()), 2)

    bal = pd.DataFrame([
        {"as_of": START - timedelta(days=1), "account": "Current account", "balance": profile.opening},
        {"as_of": date(2026, 6, 30), "account": "Current account", "balance": balance_on(date(2026, 6, 30))},
    ])
    for df, cols in ((led, ["date"]), (obl, ["issue_date", "due_date", "paid_date"]), (bal, ["as_of"])):
        for c in cols:
            df[c] = pd.to_datetime(df[c])
    led["reference"] = led["reference"].fillna("")
    return {"ledger": led, "obligations": obl, "balances": bal}
