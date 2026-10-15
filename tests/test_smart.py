"""Health score, weekly story, budgets & goals, calendar & GST, what-ifs and reports — hand-checked where possible."""

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from finpilot.api import dataset
from finpilot.api.server import create_app
from finpilot.engine import budget, calendar_gst as cg, reports, whatif
from finpilot.engine.decision import emi
from finpilot.engine.health import health_score, obligations_as_of, points
from finpilot.engine.story import weekly_story

A = "2026-09-30"


class TestHealth:
    def test_scales(self):
        assert points("cash", 0) == 0 and points("cash", 3) == 20 and points("cash", 10) == 20
        assert points("cash", 1.5) == 13.5  # halfway between 1 month (11) and 2 months (16)
        assert points("collections", 0) == 20 and points("collections", 100) == 0
        assert points("momentum", -5) == 10.0

    def test_demo_score_components(self, demo):
        h = health_score(demo["ledger"], demo["balances"], demo["obligations"], A)
        by = {c["key"]: c for c in h["components"]}
        assert by["cash"]["value"] == 2.2 and by["momentum"]["value"] < -15
        assert by["collections"]["value"] == pytest.approx(383000 / 1079000 * 100, abs=0.1)
        assert h["score"] == round(sum(c["points"] for c in h["components"]))
        assert h["history"][-1]["score"] == h["score"] and len(h["history"]) >= 3

    def test_history_uses_status_at_that_date(self, tiny):
        o = obligations_as_of(tiny["obligations"], pd.Timestamp("2026-02-15"))
        # INV-0 was issued 1 Feb and paid 2 Mar, so on 15 Feb it was still pending; INV-1 (issued 1 Apr) didn't exist yet.
        assert set(o["item_id"]) == {"INV-0", "BILL-1"} and o.set_index("item_id").loc["INV-0", "status"] == "pending"

    def test_no_balance_scores_zero_for_cash(self, demo):
        h = health_score(demo["ledger"], None, demo["obligations"], A, with_history=False)
        assert next(c for c in h["components"] if c["key"] == "cash")["points"] == 0


def test_weekly_story_matches_ledger(demo):
    s = weekly_story(demo["ledger"], demo["obligations"], A)
    led = demo["ledger"]
    w = led[(led["date"] >= "2026-09-24") & (led["date"] <= A)]
    assert s["this"]["money_in"] == pytest.approx(w.loc[w.direction == "in", "amount"].sum())
    assert s["this"]["money_out"] == pytest.approx(w.loc[w.direction == "out", "amount"].sum())
    assert s["net"] == pytest.approx(s["this"]["money_in"] - s["this"]["money_out"])
    assert s["best_day"]["weekday"] == "Saturday"


class TestBudgets:
    def test_suggest_rounds_up_average(self, tiny):
        # last 3 full months to 30 Apr: Feb–Apr. Raw materials 30k + 45k = 75k / 3 = 25k; rent 40k / 3 = 13,333 → 13,500.
        s = budget.suggest_budgets(tiny["ledger"], "2026-04-30")
        assert s["Raw materials"] == 25_000 and s["Rent"] == 13_500

    def test_status_and_pace(self, tiny):
        st = budget.budget_status(tiny["ledger"], {"Raw materials": 40_000, "Rent": 30_000}, "2026-04-15")
        rows = {r["category"]: r for r in st["rows"]}
        # April to the 15th: raw materials 45k (over), rent 20k → pace 20k/15×30 = 40k > 30k → near
        assert rows["Raw materials"]["state"] == "over" and rows["Raw materials"]["left"] == -5000
        assert rows["Rent"]["pace"] == 40_000 and rows["Rent"]["state"] == "near"

    def test_goal_plan(self):
        g = budget.goal_plan({"name": "Diwali stock", "target": 120_000, "saved": 30_000, "target_date": "2026-12-31"}, A)
        assert g["months_left"] == 3 and g["per_month"] == 30_000 and g["pct"] == 25.0


class TestCalendarGst:
    def test_statutory_dates(self):
        m = {d["title"]: d["day"] for d in cg.statutory_dates(2026, 10)}
        assert m["GSTR-1"] == 11 and m["GSTR-3B + GST payment"] == 20 and m["TDS deposit for last month"] == 7
        q = {d["title"] for d in cg.statutory_dates(2026, 10, "qrmp")}
        assert "GSTR-3B (quarterly) + GST payment" in q
        assert "Advance income tax instalment" in {d["title"] for d in cg.statutory_dates(2026, 12)}
        assert not any("GST" in d["title"] for d in cg.statutory_dates(2026, 10, registered=False))

    def test_gst_math(self, tiny):
        # April: sales 120k incl. 5% → output 120000×5/105; purchases: raw materials 45k + rent 20k → input 65000×5/105
        g = cg.gst_estimate(tiny["ledger"], "2026-04-01", "2026-04-30", 5, 5)
        assert g["output_gst"] == pytest.approx(120000 * 5 / 105, abs=0.01)
        assert g["input_credit"] == pytest.approx(65000 * 5 / 105, abs=0.01)
        assert g["estimated_payable"] == pytest.approx((120000 - 65000) * 5 / 105, abs=0.01)

    def test_month_calendar(self, demo):
        c = cg.month_calendar(demo["ledger"], demo["obligations"], A, 2026, 10)
        kinds = {e["kind"] for d in c["days"] for e in d["events"]}
        assert {"receivable", "payable", "tax"} <= kinds
        assert len(c["days"]) == 31 and c["first_weekday"] == 3  # 1 Oct 2026 is a Thursday
        sept = cg.month_calendar(demo["ledger"], demo["obligations"], A, 2026, 9)
        led = demo["ledger"]
        m = led[(led["date"] >= "2026-09-01") & (led["date"] <= A)]
        assert sept["money_in"] == pytest.approx(m.loc[m.direction == "in", "amount"].sum())


class TestWhatIf:
    def test_price_change_arithmetic(self, demo):
        b = whatif.baseline(demo["ledger"], A)
        r = whatif.price_change(demo["ledger"], A, 5, -3)
        S, V, F = b["sales"], b["variable"], b["fixed"]
        assert r["new_profit"] == pytest.approx(S * 1.05 * 0.97 - V * 0.97 - F, abs=0.02)
        be = whatif.price_change(demo["ledger"], A, 5, r["breakeven_volume_pct"])
        assert be["monthly_change"] == pytest.approx(0, abs=S * 0.002)  # break-even holds (rounded %)

    def test_discount_needs_uplift(self, demo):
        r = whatif.discount(demo["ledger"], A, 10, 0, 4)
        assert r["profit_change"] < 0 and r["uplift_needed_pct"] > 10
        ok = whatif.discount(demo["ledger"], A, 10, r["uplift_needed_pct"], 4)
        assert ok["profit_change"] == pytest.approx(0, abs=200)

    def test_hire_and_loan(self, demo):
        h = whatif.hire(demo["ledger"], demo["balances"], demo["obligations"], A, 18_000, 0)
        assert h["monthly_change"] == -18_000 and h["cash"]["end_with"] < h["cash"]["end_without"]
        ln = whatif.loan(demo["ledger"], demo["balances"], demo["obligations"], A, 500_000, 12, 3)
        assert ln["emi"] == emi(500_000, 12, 36) and ln["total_interest"] == pytest.approx(ln["emi"] * 36 - 500_000, abs=0.01)


def test_reports(demo):
    m = reports.monthly(demo["ledger"], demo["balances"], demo["obligations"], A, 2026, 9)
    assert m["closing_balance"] == 1_485_414 and m["summary"]["revenue"] == 579_876
    assert m["opening_balance"] - m["closing_balance"] == pytest.approx(-m["summary"]["net_cash_movement"], abs=0.01)
    lr = reports.loan_readiness(demo["ledger"], demo["balances"], demo["obligations"], A)
    assert lr["level"] in ("strong", "fair", "weak") and len(lr["checks"]) == 6 and lr["passed"] == sum(c["ok"] for c in lr["checks"])


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FINPILOT_AI", "off")
    monkeypatch.setattr(dataset, "today", lambda: pd.Timestamp("2026-09-30"))
    return TestClient(create_app(tmp_path / "s.db", static_dir=None))


class TestSmartApi:
    def test_endpoints_in_english_and_hindi(self, client):
        for path in ("/api/health", "/api/story", "/api/budgets", "/api/goals", "/api/calendar", "/api/settings", "/api/reports/months",
                     "/api/reports/monthly?month=2026-09", "/api/reports/loan", "/api/whatif/price?price_pct=5&volume_pct=-2",
                     "/api/whatif/discount", "/api/whatif/hire?salary=15000", "/api/whatif/loan?amount=300000&rate=11&years=2"):
            assert client.get(path).status_code == 200, path
        h = client.get("/api/home", headers={"X-Lang": "hi"}).json()
        assert h["status"]["headline"] == "आपका कारोबार अच्छी हालत में है"
        assert any("बाकी" in a["title"] for a in h["attention"])
        assert client.get("/api/health", headers={"X-Lang": "hi"}).json()["components"][0]["label"] == "कैश की सुरक्षा"
        cal = client.get("/api/calendar?year=2026&month=10", headers={"X-Lang": "hi"}).json()
        assert cal["label"] == "अक्टूबर 2026"

    def test_budgets_goals_settings_roundtrip(self, client):
        sug = client.get("/api/budgets").json()["suggested"]
        assert "Raw materials" in sug
        b = client.post("/api/budgets", json={"limits": {"Raw materials": 250000, "Marketing": 5000}}).json()
        assert b["limits"]["Marketing"] == 5000 and "Raw materials" in b["status"]["over"]
        assert any(a["id"].startswith("budget-") for a in client.get("/api/home").json()["attention"])
        client.post("/api/budgets", json={"limits": {"Marketing": None}})
        assert "Marketing" not in client.get("/api/budgets").json()["limits"]
        g = client.post("/api/goals", json={"name": "GST set-aside", "target": 60000, "target_date": "2026-12-31"}).json()
        gid = g[0]["id"]
        g = client.post(f"/api/goals/{gid}", json={"add": 15000}).json()
        assert g[0]["saved"] == 15000 and g[0]["per_month"] == 15000
        assert client.post("/api/goals", json={"target": 0}).status_code == 400
        s = client.post("/api/settings", json={"gst_rate_sales": 12, "gst_filing": "qrmp"}).json()
        assert s["gst_rate_sales"] == "12.0" and s["gst_filing"] == "qrmp"
        assert client.post("/api/settings", json={"gst_rate_sales": 50}).status_code == 400

    def test_ask_in_hindi_mode_still_verified(self, client):
        r = client.post("/api/ask", json={"question": "How much cash do we have?"}, headers={"X-Lang": "hi"}).json()
        assert r["verified"] and r["steps"][0]["label"] == "बैंक बैलेंस जाँचा"
