"""Quick entries, udhaar settlement and undo, the entry parser, bank-line categorising, and the khata API."""

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from finpilot.api import dataset
from finpilot.api.server import create_app
from finpilot.data import khata
from finpilot.data.parse_entry import parse
from finpilot.engine.cash import cash_position, obligations_status
from finpilot.engine.categorize import categorize, extract_party
from finpilot.engine.summary import financial_summary


@pytest.fixture
def t(tiny):
    return khata.Tables(tiny["ledger"].copy(), tiny["obligations"].copy(), tiny["balances"].copy())


AS_OF = "2026-04-30"


class TestRecord:
    def test_sale_is_revenue_and_cash(self, t, tiny):
        r = khata.record(t, "sale", 5000, AS_OF, party="Ravi", mode="upi", as_of=AS_OF)
        assert r.entry_id == "E00001"
        s = financial_summary(r.tables.ledger)
        assert s["revenue"] == 220_000 + 5000
        assert cash_position(r.tables.ledger, tiny["balances"], AS_OF)["cash_balance"] == 152_000 + 5000

    def test_udhaar_is_not_revenue_until_paid(self, t):
        r = khata.record(t, "credit_sale", 8000, AS_OF, party="Ravi", as_of=AS_OF)
        assert financial_summary(r.tables.ledger)["revenue"] == 220_000  # no money yet
        st = obligations_status(r.tables.obligations, AS_OF)
        assert st["receivables"]["pending_not_due"] == 25_000 + 8000
        due = r.tables.obligations.set_index("item_id").loc[r.entry_id, "due_date"]
        assert str(due.date()) == "2026-05-15"  # 15 days by default

    def test_part_payment_splits_and_full_payment_clears(self, t):
        # Customer C has INV-1 (40k, overdue). Pay 15k then 25k.
        r1 = khata.record(t, "payment_in", 15_000, AS_OF, party="C", as_of=AS_OF)
        o = r1.tables.obligations.set_index("item_id")
        assert o.loc["INV-1", "amount"] == 25_000 and o.loc["INV-1", "status"] == "pending"
        assert o.loc["INV-1-P1", "amount"] == 15_000 and o.loc["INV-1-P1", "status"] == "paid"
        assert r1.settled == [{"item_id": "INV-1", "amount": 15_000, "full": False}]
        r2 = khata.record(r1.tables, "payment_in", 25_000, AS_OF, party="c", as_of=AS_OF)
        assert r2.tables.obligations.set_index("item_id").loc["INV-1", "status"] == "paid"
        # receipts counted once as revenue; nothing double counted
        assert financial_summary(r2.tables.ledger)["revenue"] == 220_000 + 40_000
        st = obligations_status(r2.tables.obligations, AS_OF)
        assert st["receivables"]["overdue"] == 0

    def test_overpayment_is_reported(self, t):
        r = khata.record(t, "payment_in", 50_000, AS_OF, party="C", as_of=AS_OF)
        assert r.unapplied == 10_000

    def test_bill_payment_uses_bill_category(self, t):
        r = khata.record(t, "payment_out", 15_000, AS_OF, party="Supplier", as_of=AS_OF)
        row = r.tables.ledger.iloc[-1]
        assert row["direction"] == "out" and row["category"] == "Raw materials"
        assert r.tables.obligations.set_index("item_id").loc["BILL-2", "status"] == "paid"

    def test_undo_restores_exactly(self, t):
        r = khata.record(t, "payment_in", 15_000, AS_OF, party="C", as_of=AS_OF)
        back = khata.undo(r.tables, r.undo)
        assert len(back.ledger) == len(t.ledger)
        a = back.obligations.sort_values("item_id").reset_index(drop=True)
        b = t.obligations.sort_values("item_id").reset_index(drop=True)
        assert list(a["item_id"]) == list(b["item_id"]) and list(a["status"]) == list(b["status"])
        assert [float(x) for x in a["amount"]] == [float(x) for x in b["amount"]]

    @pytest.mark.parametrize("kw,msg", [
        ({"amount": 0}, "above zero"), ({"amount": "abc"}, "number"), ({"kind": "credit_sale", "party": ""}, "Whose name"),
        ({"date": "2026-05-10"}, "can't be after"), ({"kind": "bill", "party": "X", "due_date": "2026-01-01"}, "before the entry"),
    ])
    def test_validation(self, t, kw, msg):
        args = {"kind": "sale", "amount": 100, "date": AS_OF} | kw
        with pytest.raises(khata.EntryError, match=msg):
            khata.record(t, args.pop("kind"), args.pop("amount"), args.pop("date"), as_of=AS_OF, **args)


class TestParse:
    @pytest.mark.parametrize("text,kind,amount,party", [
        ("sold masala to Ravi 2500 cash", "sale", 2500, "Ravi"),
        ("Ravi ko 3000 udhaar", "credit_sale", 3000, "Ravi"),
        ("Ravi ne 1500 diye upi", "payment_in", 1500, "Ravi"),
        ("received 12,000 from Metro Foods via NEFT", "payment_in", 12000, "Metro Foods"),
        ("paid rent 55000", "expense", 55000, ""),
        ("bill from Kisan Agro 40k due 20 oct", "bill", 40000, "Kisan Agro"),
        ("kal 2 lakh ka maal becha Sharma Traders ko udhaar due in 30 days", "credit_sale", 200000, "Sharma Traders"),
    ])
    def test_cases(self, text, kind, amount, party):
        r = parse(text, "2026-09-30")
        assert (r["kind"], r["amount"], r["party"]) == (kind, amount, party)

    def test_details(self):
        assert parse("bijli bill 4200", "2026-09-30")["category"] == "Electricity"
        assert parse("sold haldi 3400 gpay", "2026-09-30")["mode"] == "upi"
        assert parse("kal sale 500", "2026-09-30")["date"] == "2026-09-29"
        assert parse("bill from Kisan Agro 40k due 20 oct", "2026-09-30")["due_date"] == "2026-10-20"
        assert parse("ravi ko 500 udhaar", "2026-09-30", ["Ravi Kumar"])["party"] == "Ravi Kumar"
        assert "amount" in parse("sold to Ravi", "2026-09-30")["missing"]


class TestCategorize:
    @pytest.mark.parametrize("line,direction,party,cat", [
        ("UPI/RAVI KUMAR/ravi@okaxis/Payment", "in", "Ravi Kumar", "Sales"),
        ("NEFT-HDFCN52023091512-MSEDCL LTD-ELEC BILL", "out", "Msedcl Ltd", "Electricity"),
        ("ACH D- TP ACH ICICI BANK-LOAN EMI 123456", "out", None, "Loan EMI"),
        ("ATM WDL 12345 PUNE", "out", None, "Transfer"),
        ("GST PAYMENT CBIC CPIN 1234", "out", None, "GST Payment"),
        ("SALARY SEPT STAFF", "out", None, "Salaries"),
    ])
    def test_rules(self, line, direction, party, cat):
        if party:
            assert extract_party(line) == party
        assert categorize(line, direction, extract_party(line))["category"] == cat

    def test_incoming_is_only_a_guess_and_learned_rules_win(self):
        g = categorize("UPI/ASHA MART/x@ybl", "in", "Asha Mart")
        assert g["confidence"] == "guess"
        assert categorize("UPI/ASHA MART/x@ybl", "in", "Asha Mart", {"asha mart": "Loan Received"})["category"] == "Loan Received"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FINPILOT_AI", "off")
    monkeypatch.setattr(dataset, "today", lambda: pd.Timestamp("2026-09-30"))
    return TestClient(create_app(tmp_path / "k.db", static_dir=None))


class TestKhataApi:
    def test_entry_changes_home_and_undo(self, client):
        cash0 = client.get("/api/home").json()["cash"]["amount"]
        r = client.post("/api/entries", json={"kind": "sale", "amount": 2500, "party": "Ravi", "mode": "cash"}).json()
        assert r["id"].startswith("E") and "Sale" in r["message"]
        assert client.get("/api/home").json()["cash"]["amount"] == cash0 + 2500
        assert client.get("/api/entries").json()["entries"][0]["id"] == r["id"]
        assert client.post(f"/api/entries/{r['id']}/undo").json()["ok"]
        assert client.get("/api/home").json()["cash"]["amount"] == cash0
        assert client.post(f"/api/entries/{r['id']}/undo").status_code == 404

    def test_collect_udhaar_from_customer(self, client):
        p = client.get("/api/people", params={"side": "customers"}).json()
        metro = next(x for x in p["people"] if x["name"] == "Metro Foods Pvt Ltd")
        assert metro["overdue"] == 294_000 and metro["reliability"]["count"] >= 2
        client.post("/api/entries", json={"kind": "payment_in", "amount": 100_000, "party": "Metro Foods Pvt Ltd", "mode": "bank"})
        metro2 = client.get("/api/person", params={"name": "Metro Foods Pvt Ltd"}).json()
        assert metro2["overdue"] == 194_000
        assert metro2["timeline"][0]["type"] == "payment_in"

    def test_promise_and_contact(self, client):
        client.post("/api/person/promise", json={"name": "Metro Foods Pvt Ltd", "amount": 100000, "date": "2026-09-20"})
        client.post("/api/person/contact", json={"name": "Metro Foods Pvt Ltd", "phone": "98765 43210"})
        m = next(x for x in client.get("/api/people").json()["people"] if x["name"] == "Metro Foods Pvt Ltd")
        assert m["promise"]["broken"] is True and m["phone"] == "919876543210"
        r = client.post("/api/reminder", json={"customer": "Metro Foods Pvt Ltd"}).json()
        assert r["whatsapp"].startswith("https://wa.me/919876543210?text=")
        hi = client.get("/api/reminders", params={"lang": "hi"}).json()
        assert hi[0]["text"].startswith("नमस्ते")

    def test_start_fresh_and_categorise(self, client):
        client.post("/api/start", json={"name": "Sharma Store", "balance": "50,000"})
        st = client.get("/api/state").json()
        assert st["source"] == "upload" and st["business"] == "Sharma Store"
        h = client.get("/api/home").json()
        assert h["cash"]["amount"] == 50_000 and h["status"]["tone"] == "neutral"
        client.post("/api/entries", json={"kind": "sale", "amount": 1200})
        client.post("/api/entries", json={"kind": "expense", "amount": 300, "category": "Uncategorised", "party": "Chotu"})
        rv = client.get("/api/categorise/review").json()
        assert rv["count"] == 1
        g = rv["groups"][0]
        assert client.post("/api/categorise", json={"ids": g["ids"], "category": "Staff Welfare", "party": "Chotu", "remember": True}).json()["updated"] == 1
        assert client.get("/api/categorise/review").json()["count"] == 0
        assert client.post("/api/start", json={"name": "Again"}).status_code == 409

    def test_imported_statement_is_categorised_and_reviewable(self, client):
        csv = ("Date,Narration,Withdrawal,Deposit\n01/09/2026,UPI/RAVI KUMAR/r@ok,,12000\n02/09/2026,NEFT-X-MSEDCL LTD,4200,\n"
               "03/09/2026,UPI/ASHA MART/a@ybl,,8000\n")
        r = client.post("/api/upload/import", data={"kind": "bank"}, files={"file": ("s.csv", csv.encode())}).json()
        assert "Sorted 1 of 3" in r["notes"][0]
        rows = {x["party"]: x["category"] for x in client.get("/api/transactions").json()["rows"]}
        assert rows == {"Ravi Kumar": "Sales", "Msedcl Ltd": "Electricity", "Asha Mart": "Sales"}
        assert client.get("/api/categorise/review").json()["count"] == 2

    def test_demo_edits_persist_and_reset(self, client):
        client.post("/api/entries", json={"kind": "expense", "amount": 999, "category": "Marketing"})
        assert client.get("/api/transactions", params={"q": "Marketing"}).json()["rows"][0]["amount"] == 999
        client.post("/api/demo/reset")
        assert client.get("/api/transactions", params={"ids": "E00001"}).json()["total"] == 0


def test_parse_hindi_units():
    r = parse("Ravi ko 2 हज़ार udhaar", "2026-09-30")
    assert (r["kind"], r["amount"], r["party"]) == ("credit_sale", 2000, "Ravi")
    assert parse("aaj 1.5 लाख ki bikri", "2026-09-30")["amount"] == 150_000
