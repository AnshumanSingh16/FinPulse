"""Trust features: the sales investigation, honest cash labels, "Show me why" proofs, proactive alerts,
the two-week scenario and follow-through on approved actions."""

import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from finpilot.api import dataset
from finpilot.api.server import create_app
from finpilot.engine import investigate

AS_OF = pd.Timestamp("2026-09-30")


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("FINPILOT_AI", "off")
    monkeypatch.setenv("FINPILOT_ENV_FILE", str(tmp_path / "test.env"))
    monkeypatch.setattr(dataset, "today", lambda: AS_OF)
    return TestClient(create_app(tmp_path / "t.db", static_dir=None))


def tables(name):
    return dataset._demo_tables(name)


# ---------------------------------------------------------------- the sales investigation


@pytest.mark.parametrize("name", ["demo", "demo_agency", "demo_cafe"])
def test_sales_causes_add_up_to_the_change(name):
    t = tables(name)
    r = investigate.sales_change(t["ledger"], t["obligations"], AS_OF)
    assert r["status"] == "ok"
    parts = sum(d["amount"] for d in r["drivers"] if not d.get("overlay"))
    assert parts == pytest.approx(r["sales"]["change"], abs=1)
    assert sum(c["change"] for c in r["customers"]) + (r["pooled"]["change"] if r["pooled"] else 0) == pytest.approx(r["sales"]["change"], abs=1)
    if r["mix"]:
        named = sum(c["change"] for c in r["customers"])
        assert r["mix"]["count_effect"] + r["mix"]["size_effect"] == pytest.approx(named, abs=1)
    # the books start in Oct 2025, so seasonality can't be checked — and it says so
    assert not r["seasonal"]["available"]
    assert any("seasonal" in u for u in r["unverified"]) and any("products" in u for u in r["unverified"])


def test_late_money_is_told_apart_from_lost_business():
    t = tables("demo")
    r = investigate.sales_change(t["ledger"], t["obligations"], AS_OF)
    by = {c["party"]: c for c in r["customers"]}
    assert by["Metro Foods Pvt Ltd"]["kind"] == "stopped" and by["Metro Foods Pvt Ltd"]["unpaid_due"] == 294000
    assert by["Kumar Wholesale"]["kind"] == "stopped" and by["Kumar Wholesale"]["unpaid_due"] == 0


def test_mid_month_compares_like_for_like_days():
    t = tables("demo")
    r = investigate.sales_change(t["ledger"], t["obligations"], pd.Timestamp("2026-09-15"))
    assert r["period"]["current"] == ["2026-09-01", "2026-09-15"] and r["period"]["previous"] == ["2026-08-01", "2026-08-15"]
    assert r["period"]["partial_month"]


def test_why_are_sales_less_answer_is_an_investigation_and_verified(app):
    r = app.post("/api/ask", json={"question": "Why are my sales less this month?"}).json()
    assert r["verified"], r["warnings"]
    a = r["answer"]
    assert "Where the difference comes from" in a and "What I couldn't verify" in a
    assert "late money, not lost business" in a and "Metro Foods Pvt Ltd" in a
    assert "Kumar Wholesale" in a and "stopped buying" in a
    ev = r["evidence"][0]
    assert ev["unverified"] and ev["formula"] and ev["record_count"] > 0
    hi = app.post("/api/ask", json={"question": "इस महीने बिक्री कम क्यों है?", "lang": "hi"}, headers={"X-Lang": "hi"}).json()
    assert hi["verified"] and "जो मैं जाँच नहीं पाया" in hi["answer"]


def test_cash_difference_is_not_called_profit(app):
    a = app.post("/api/ask", json={"question": "How are my sales this month?"}).json()["answer"]
    assert "Net operating cash difference" in a and "not accounting profit" in a
    assert "Profit (estimate)" not in a
    assert "Why it isn't profit" in a


# ---------------------------------------------------------------- show me why


@pytest.mark.parametrize("name", ["demo", "demo_agency", "demo_cafe"])
def test_every_recommendation_can_be_proved(app, name):
    app.post("/api/source", json={"source": name})
    p = app.get("/api/autopilot").json()
    assert p["moves"]
    for m in p["moves"]:
        r = app.get("/api/prove", params={"move": m["id"]}).json()
        assert r["status"] == "ok" and r["claim"] and r["formula"] and r["assumptions"] and r["unverified"], m["id"]
        assert r["record_count"] == len(r["record_ids"])
        if m["kind"] == "collect":
            assert [x["id"] for x in r["records"][: len(m["items"])]] == m["items"], "the overdue invoices come first"
        if m["kind"] == "pause":
            kept = m["monthly"] * 12 / 365 * 60
            assert kept == pytest.approx(m["amount"], abs=1)
    assert app.get("/api/prove", params={"move": "collect:Nobody"}).status_code == 404


# ---------------------------------------------------------------- proactive alerts


def test_alerts_come_with_proof_and_next_steps(app):
    app.post("/api/source", json={"source": "demo"})
    p = app.get("/api/autopilot").json()
    ids = [a["id"] for a in p["alerts"]]
    assert "overdue" in ids and "sales_drop" in ids
    for a in p["alerts"]:
        assert a["title"] and a["detail"] and a["actions"]
        assert a["evidence"]["formula"] and a["evidence"]["method"]
    drop = next(a for a in p["alerts"] if a["id"] == "sales_drop")
    assert "Metro Foods Pvt Ltd" in drop["detail"]


def test_next_week_squeeze_is_flagged_before_it_happens(app):
    app.post("/api/source", json={"source": "demo"})
    assert "next_week" not in [a["id"] for a in app.get("/api/autopilot").json()["alerts"]]
    app.post("/api/events", json={"label": "Machine deposit", "amount": 2000000, "direction": "out", "date": "2026-10-05"})
    p = app.get("/api/autopilot").json()
    a = next(a for a in p["alerts"] if a["id"] == "next_week")
    assert a["tone"] == "bad" and "next week" in a["title"]
    assert a["actions"][0]["do"] == "fix"


# ---------------------------------------------------------------- cash in two weeks


def test_two_week_outlook_adds_up_and_matches_the_forecast(app):
    app.post("/api/source", json={"source": "demo_agency"})
    r = app.post("/api/outlook", json={}).json()
    assert r["status"] == "ok" and r["end_date"] == "2026-10-14"
    assert sum(w["amount"] for w in r["waterfall"]) == pytest.approx(r["end"], abs=2)
    assert r["daily"][-1]["balance"] == pytest.approx(r["end"], abs=1)
    over = {o["id"]: o["amount"] for o in r["overdue"]}
    assert set(over) == {"INV-0057", "INV-0063"}
    r2 = app.post("/api/outlook", json={"overdue_pay": ["INV-0057"], "purchase": {"amount": 100000, "date": "2026-10-03"}}).json()
    assert r2["end"] == pytest.approx(r["end"] + over["INV-0057"] - 100000, abs=2)
    bill = next(i for i in r["items"] if i["group"] == "bill")
    r3 = app.post("/api/outlook", json={"skip": [bill["id"]]}).json()
    assert r3["end"] == pytest.approx(r["end"] - bill["amount"], abs=2)
    assert app.post("/api/outlook", json={"purchase": {"amount": "lots"}}).status_code == 400


def test_outlook_includes_approved_moves_without_double_counting(app):
    app.post("/api/source", json={"source": "demo_agency"})
    before = app.post("/api/outlook", json={}).json()
    app.post("/api/autopilot/approve-suggested")
    after = app.post("/api/outlook", json={}).json()
    assert after["overdue"] == [], "Kaveri's invoices are already counted by the approved collection"
    assert any(w["key"] == "approved" for w in after["waterfall"]) and after["end"] > before["end"]


# ---------------------------------------------------------------- follow-through


def _ff(c, days, scenario):
    with c.stream("POST", "/api/demo/fast-forward/stream", json={"days": days, "scenario": scenario}) as r:
        return [json.loads(line[6:]) for line in r.iter_lines() if line.startswith("data: ")]


def test_follow_through_reports_what_happened(app):
    app.post("/api/source", json={"source": "demo_agency"})
    assert app.get("/api/autopilot").json()["follow_through"] == []
    app.post("/api/autopilot/approve-suggested")
    ft = {f["move_id"]: f for f in app.get("/api/autopilot").json()["follow_through"]}
    assert ft["collect:Kaveri Hospitals"]["status"] == "waiting"
    _ff(app, 14, "pays")
    ft = {f["move_id"]: f for f in app.get("/api/autopilot").json()["follow_through"]}
    k = ft["collect:Kaveri Hospitals"]
    assert k["status"] == "done" and "paid" in k["result"]
    assert ft["pause:Marketing"]["status"] in ("done", "slipped")


# ---------------------------------------------------------------- the timeline by month and quarter


@pytest.mark.parametrize("by", ["month", "quarter"])
def test_timeline_periods_add_up_and_join_the_forecast_at_today(app, by):
    app.post("/api/source", json={"source": "demo_agency"})
    p = app.get("/api/autopilot").json()
    r = app.get("/api/timeline", params={"by": by}).json()
    assert r["status"] == "ok" and r["by"] == by
    per = r["periods"]
    assert len(per) == (15 if by == "month" else 5)
    for x in per:
        assert x["opening"] + x["money_in"] - x["money_out"] == pytest.approx(x["closing"], abs=1), x["label"]
    for a, b in zip(per, per[1:]):
        assert a["closing"] == pytest.approx(b["opening"], abs=1)
    sep = next(x for x in per if x["kind"] == "actual" and x["end"] >= "2026-09-30") if by == "month" else next(x for x in per if x["label"] == "Q3 2026")
    assert sep["closing"] == pytest.approx(p["today"], abs=1), "the past ends at today's cash"
    assert min(x["lowest"] for x in per if x["kind"] != "actual") == pytest.approx(p["baseline"]["lowest"], abs=1), "the forecast is the plan's own"
    assert [x["kind"] for x in per].count("actual") == (12 if by == "month" else 4)
    assert app.get("/api/timeline", params={"by": "year"}).status_code == 422
