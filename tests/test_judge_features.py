"""Features that answer judges' questions: things the owner knows are coming, UPI pay links, the audit log."""

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from finpilot.api.server import create_app

AS_OF = pd.Timestamp("2026-09-30")


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("FINPILOT_AI", "off")
    monkeypatch.setenv("FINPILOT_ENV_FILE", str(tmp_path / "test.env"))
    from finpilot.api import dataset

    monkeypatch.setattr(dataset, "today", lambda: AS_OF)
    return TestClient(create_app(tmp_path / "t.db", static_dir=None))


def test_known_event_changes_the_forecast_plan_and_feed(app):
    app.post("/api/source", json={"source": "demo_cafe"})
    before = app.get("/api/autopilot").json()
    assert not before["baseline"]["safe"]
    r = app.post("/api/events", json={"label": "Diwali rush", "amount": 400000, "direction": "in", "date": "2026-10-25"})
    assert r.status_code == 200 and r.json()["events"][0]["amount"] == 400000
    after = app.get("/api/autopilot").json()
    assert after["events"][0]["label"] == "Diwali rush"
    assert after["baseline"]["lowest"] > before["baseline"]["lowest"]
    assert after["changes"], "telling FinPilot about an event should show up in 'what changed'"
    assert any("Diwali rush" in a["text"] for a in after["activity"])
    eid = after["events"][0]["id"]
    app.delete(f"/api/events/{eid}")
    again = app.get("/api/autopilot").json()
    assert again["events"] == [] and again["baseline"]["lowest"] == pytest.approx(before["baseline"]["lowest"], abs=1)


def test_known_event_going_out_is_counted_in_affordability(app):
    app.post("/api/source", json={"source": "demo"})
    plain = app.post("/api/autopilot/afford", json={"amount": 300000, "date": "2026-10-15"}).json()
    app.post("/api/events", json={"label": "New packing machine", "amount": 600000, "direction": "out", "date": "2026-10-10"})
    loaded = app.post("/api/autopilot/afford", json={"amount": 300000, "date": "2026-10-15"}).json()
    assert loaded["without_moves"]["lowest"] < plain["without_moves"]["lowest"] - 500000


@pytest.mark.parametrize("body", [
    {"label": "", "amount": 1000, "date": "2026-10-10"},
    {"label": "x", "amount": 0, "date": "2026-10-10"},
    {"label": "x", "amount": 1000, "date": "2027-06-01"},
    {"label": "x", "amount": 1000, "date": "2026-09-01"},
    {"label": "x", "amount": 1000, "date": "someday"},
])
def test_event_validation(app, body):
    assert app.post("/api/events", json=body).status_code == 400


def test_reminders_carry_a_upi_pay_link(app):
    app.post("/api/source", json={"source": "demo_agency"})
    r = app.post("/api/reminder", json={"customer": "Kaveri Hospitals"}).json()
    assert "pixelpundit@demo" in r["text"] and "upi://pay?pa=pixelpundit%40demo" in r["text"] and "am=525600.00" in r["text"]
    assert app.post("/api/settings", json={"upi_id": "not a upi"}).status_code == 400
    assert app.post("/api/settings", json={"upi_id": "pixel.pundit@okicici"}).status_code == 200
    r = app.post("/api/reminder", json={"customer": "Kaveri Hospitals", "lang": "hi"}).json()
    assert "pixel.pundit@okicici" in r["text"] and "UPI से तुरंत भुगतान" in r["text"]


def test_audit_log_records_agents_and_owner(app):
    app.post("/api/source", json={"source": "demo_agency"})
    app.get("/api/autopilot")
    app.post("/api/autopilot/approve-suggested")
    app.post("/api/events", json={"label": "Office party", "amount": 50000, "direction": "out", "date": "2026-10-20"})
    r = app.get("/api/audit.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    body = r.content.decode("utf-8-sig")
    assert body.splitlines()[0] == "recorded_at,book_date,who,kind,what"
    assert "owner,decision,approved: collect:Kaveri Hospitals" in body
    assert "agent:collections" in body and "Office party" in body
