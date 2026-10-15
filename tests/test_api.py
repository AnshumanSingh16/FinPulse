"""Web API: owner-facing views on the demo data, uploads, to-dos, and the ask endpoint (rule-based mode)."""

import io
import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from finpilot.api import views
from finpilot.api.server import create_app
from finpilot.data.demo import DEMO_DIR
from finpilot.engine.cash import cash_position, obligations_status
from finpilot.engine.summary import financial_summary


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FINPILOT_AI", "off")
    from finpilot import config

    if hasattr(config.settings, "cache_clear"):
        config.settings.cache_clear()
    return TestClient(create_app(tmp_path / "t.db", static_dir=None))


def test_short_format():
    assert views.short(1485414) == "₹14.85 L"
    assert views.short(12_000_000) == "₹1.2 Cr"
    assert views.short(45_000) == "₹45,000"
    assert views.short(-250_000) == "−₹2.5 L"
    assert views.day("2026-10-04") == "4 Oct"


class TestHome:
    def test_numbers_come_from_the_engine(self, client, demo):
        h = client.get("/api/home").json()
        assert h["is_demo"] and h["status"]["tone"] == "good"
        cash = cash_position(demo["ledger"], demo["balances"], "2026-09-30")["cash_balance"]
        assert h["cash"]["amount"] == cash and h["cash"]["history"][-1]["balance"] == cash
        s = financial_summary(demo["ledger"], "2026-09-01", "2026-09-30")
        assert h["month"]["sales"] == s["revenue"] and h["month"]["profit"] == s["estimated_operating_profit"]
        assert h["month"]["label"] == "September 2026" and h["month"]["previous"]["label"] == "August 2026"

    def test_history_is_consistent_with_the_ledger(self, client, demo):
        h = client.get("/api/home").json()
        # Balance on 30 Jun (a statement date) must equal the stated balance.
        on = {p["date"]: p["balance"] for p in h["cash"]["history"]}
        if "2026-06-30" in on:
            assert on["2026-06-30"] == pytest.approx(float(demo["balances"].iloc[-1]["balance"]), abs=0.01)
        assert len(h["cash"]["outlook"]) == 91

    def test_attention_items(self, client):
        items = client.get("/api/home").json()["attention"]
        titles = " | ".join(i["title"] for i in items)
        assert "Metro Foods Pvt Ltd owes you" in titles
        assert "double payment" in titles
        remind = next(i for i in items if i["action"]["type"] == "remind")
        assert remind["action"]["customer"] == "Metro Foods Pvt Ltd"

    def test_cost_insight(self, client):
        ins = client.get("/api/home").json()["insight"]
        assert ins and "rose" in ins["text"] and "raw materials" in ins["text"]


def test_no_balance_is_unknown_not_guessed(tmp_path, demo):
    ds = views.Dataset("X", "upload", demo["ledger"], demo["obligations"], None, pd.Timestamp("2026-09-30"))
    h = views.home(ds)
    assert h["status"]["tone"] == "neutral" and not h["cash"]["known"] and "amount" not in h["cash"]
    assert all(a["action"]["type"] != "add_balance" for a in h["attention"])  # said once, in the headline
    assert views.forecast(ds)["status"] == "needs_balance"
    assert views.afford(ds, {"price": 100000})["status"] == "needs_balance"


class TestMoney:
    def test_transactions_filter_and_totals(self, client, demo):
        r = client.get("/api/transactions", params={"direction": "out", "category": "Logistics"}).json()
        led = demo["ledger"]
        exp = led[(led.direction == "out") & (led.category == "Logistics")]
        assert r["total"] == len(exp) and r["money_out"] == pytest.approx(exp.amount.sum(), abs=0.01)
        assert r["rows"][0]["date"] >= r["rows"][-1]["date"]
        assert client.get("/api/transactions", params={"ids": "T0338,T0339"}).json()["total"] == 2
        assert client.get("/api/transactions", params={"q": "msedcl"}).json()["total"] > 0

    def test_owed_groups_add_up(self, client, demo):
        o = client.get("/api/owed").json()
        st = obligations_status(demo["obligations"], "2026-09-30")
        assert o["customers"]["overdue"] == st["receivables"]["overdue"]
        assert sum(g["total"] for g in o["customers"]["groups"]) == pytest.approx(o["customers"]["total"], abs=0.01)
        assert o["customers"]["groups"][0]["name"] == "Metro Foods Pvt Ltd"

    def test_reminder_draft(self, client):
        r = client.post("/api/reminder", json={"customer": "Metro Foods Pvt Ltd"}).json()
        assert r["status"] == "ok" and "INV-0099" in r["text"] and r["whatsapp"].startswith("https://wa.me/?text=")
        assert "(fictional)" not in r["text"]
        assert client.post("/api/reminder", json={"customer": "Nobody"}).json()["status"] == "missing"

    def test_report(self, client):
        r = client.get("/api/report").json()
        assert r["status"] == "ok" and len(r["months"]) == 12 and r["months"][0]["month"] == "Sep 2026"


class TestPlan:
    def test_forecast_and_what_ifs(self, client):
        base = client.get("/api/forecast").json()
        late = client.get("/api/forecast", params={"late_days": 30, "collect_pct": 80}).json()
        assert base["status"] == "ok" and [c["days"] for c in base["checkpoints"]] == [30, 60, 90]
        assert late["checkpoints"][0]["balance"] < base["checkpoints"][0]["balance"]
        assert base["big_items"] and not base["big_items"][0]["what"].startswith("SCH-")

    def test_afford_loan_needs_terms(self, client):
        r = client.post("/api/afford", json={"name": "Van", "price": 800000, "paid_with": "loan"}).json()
        assert r["status"] == "needs_input"

    def test_afford(self, client):
        r = client.post("/api/afford", json={"name": "Packing machine", "price": 1200000, "paid_with": "loan", "rate": 11, "years": 3,
                                              "monthly_benefit": 45000, "running_cost": 4000, "one_time_cost": 35000}).json()
        assert r["status"] == "ok" and r["months"] == 36 and r["emi"] == pytest.approx(31429.17, abs=0.01)
        assert r["upfront"] == 240000 + 35000
        assert {s["key"] for s in r["scenarios"]} == {"base", "downside", "optimistic"}
        assert r["tone"] == "caution" and r["headline"].startswith("Yes — but")
        # Tough-months low point without any purchase is ~₹7.18 L against a ₹6.77 L cushion: ₹20k fits, ₹50k doesn't.
        assert client.post("/api/afford", json={"name": "Oven", "price": 50000, "paid_with": "cash"}).json()["tone"] == "caution"
        small = client.post("/api/afford", json={"name": "Oven", "price": 20000, "paid_with": "cash"}).json()
        assert small["tone"] == "good" and small["headline"] == "Yes, you can afford it"
        huge = client.post("/api/afford", json={"name": "Factory", "price": 30000000, "paid_with": "cash"}).json()
        assert huge["tone"] == "bad"


class TestAskAndTodos:
    def test_ask_rule_based(self, client):
        r = client.post("/api/ask", json={"question": "How much cash do we have?"}).json()
        assert r["mode"] == "rule-based" and r["verified"] and "₹14,85,414" in r["answer"]
        assert r["steps"][0]["label"] == "Checked your bank balance" and r["evidence"]

    def test_ask_validation(self, client):
        assert client.post("/api/ask", json={"question": " "}).status_code == 400

    def test_todos_never_execute(self, client):
        t = client.post("/api/todos", json={"text": "Pay PackWell ₹26,800"}).json()
        assert t[0]["status"] == "open"
        done = client.post(f"/api/todos/{t[0]['id']}", json={"status": "done"}).json()
        assert done[0]["status"] == "done"
        assert client.post(f"/api/todos/{t[0]['id']}", json={"status": "dismissed"}).status_code == 409


class TestUpload:
    def _post(self, client, kind, path, **form):
        data = {"kind": kind, **{k: (json.dumps(v) if isinstance(v, dict) else str(v)) for k, v in form.items()}}
        return client.post("/api/upload/import", data=data, files={"file": (path.name, path.read_bytes())})

    def test_inspect_suggests_columns(self, client):
        p = DEMO_DIR / "ledger.csv"
        r = client.post("/api/upload/inspect", data={"kind": "bank"}, files={"file": (p.name, p.read_bytes())}).json()
        assert r["mapping"]["date"] == "date" and r["mapping"]["amount"] == "amount" and not r["missing"]

    def test_full_upload_matches_demo(self, client, demo):
        for kind, f in (("bank", "ledger.csv"), ("invoices", "obligations.csv"), ("balances", "balances.csv")):
            r = self._post(client, kind, DEMO_DIR / f, business="My Masala Co")
            assert r.status_code == 200, r.text
        st = client.get("/api/state").json()
        assert st["source"] == "upload" and st["business"] == "My Masala Co" and st["upload"]["bank_rows"] == len(demo["ledger"])
        h = client.get("/api/home").json()
        assert not h["is_demo"] and h["cash"]["exact"] == "₹14,85,414"

    def test_plain_bank_statement_and_manual_balance(self, client):
        csv = "Txn Date,Narration,Withdrawal,Deposit\n01/09/2026,UPI from Ravi,,12000\n03/09/2026,Rent,15000,\n05/09/2026,UPI from Asha,,8000\n"
        r = client.post("/api/upload/import", data={"kind": "bank"}, files={"file": ("stmt.csv", csv.encode())})
        assert r.status_code == 200, r.text
        assert "counted as sales" in r.json()["notes"][0]
        h = client.get("/api/home").json()
        assert not h["cash"]["known"] and h["status"]["tone"] == "neutral"
        client.post("/api/balance", json={"date": "2026-09-05", "amount": "₹50,000"})
        h = client.get("/api/home").json()
        assert h["cash"]["known"] and h["cash"]["amount"] == 50_000
        assert h["month"]["sales"] == 20_000  # both deposits, as sales

    def test_invoice_list_without_type_column(self, client):
        csv = "Invoice No,Customer,Amount,Due Date\nA-1,Ravi Stores,10000,2026-08-01\nA-2,Asha Mart,5000,2026-12-01\n"
        self._post_bytes = None
        r = client.post("/api/upload/import", data={"kind": "invoices", "invoice_kind": "customers"}, files={"file": ("inv.csv", csv.encode())})
        assert r.status_code == 200, r.text
        assert "2 from customers" in r.json()["summary"]

    def test_bad_upload_messages(self, client):
        r = client.post("/api/upload/import", data={"kind": "bank"}, files={"file": ("x.csv", b"foo,bar\n1,2\n")})
        assert r.status_code == 400 and "choose a column" in r.json()["detail"]
        assert client.post("/api/source", json={"source": "upload"}).status_code == 400
        assert client.delete("/api/upload").json()["source"] == "demo"
