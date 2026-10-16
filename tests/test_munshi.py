"""Munshi's chat thread: the lena/dena strip, the persistent conversation, entries as khata lines, and the once-a-day check-up."""

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from finpilot.api.server import create_app
from finpilot.engine.cash import cash_position, obligations_status

AS_OF = pd.Timestamp("2026-09-30")


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("FINPILOT_AI", "off")
    monkeypatch.setenv("FINPILOT_ENV_FILE", str(tmp_path / "test.env"))
    from finpilot.api import dataset

    monkeypatch.setattr(dataset, "today", lambda: AS_OF)
    return TestClient(create_app(tmp_path / "t.db", static_dir=None))


def test_lena_dena_strip_matches_the_engine(app, demo):
    s = app.get("/api/chat").json()["snapshot"]
    assert s["cash"] == cash_position(demo["ledger"], demo["balances"], AS_OF)["cash_balance"]
    o = obligations_status(demo["obligations"], AS_OF)
    assert s["to_collect"] == pytest.approx(o["receivables"]["pending_not_due"] + o["receivables"]["overdue"])
    assert s["to_pay"] == pytest.approx(o["payables"]["pending_not_due"] + o["payables"]["overdue"])
    assert s["collect_overdue"] == o["receivables"]["overdue"]


def test_conversation_is_kept_and_actions_come_back_with_their_state(app):
    assert app.get("/api/chat").json()["items"] == []
    r = app.post("/api/ask", json={"question": "add a sale of 500 cash", "conversation_id": "main", "log": True}).json()
    app.post(f"/api/agent/actions/{r['actions'][0]['id']}", json={"conversation_id": "main"})
    items = app.get("/api/chat").json()["items"]
    assert [(i["role"], i["kind"]) for i in items] == [("owner", "text"), ("munshi", "answer"), ("event", "entry")]
    assert items[0]["data"]["text"] == "add a sale of 500 cash"
    assert items[1]["data"]["actions"][0]["state"] == "done"  # read back live from the database
    assert items[2]["data"]["message"].startswith("Sale ₹500")


def test_unlogged_asks_stay_out_of_the_thread(app):
    app.post("/api/ask", json={"question": "who owes me?"})
    assert app.get("/api/chat").json()["items"] == []


def test_every_entry_becomes_a_khata_line_and_undo_marks_it(app):
    before = app.get("/api/chat").json()["snapshot"]["to_collect"]
    e = app.post("/api/entries", json={"kind": "credit_sale", "amount": 2500, "party": "Ravi"}).json()
    c = app.get("/api/chat").json()
    line = c["items"][-1]
    assert line["kind"] == "entry" and line["data"]["entry_id"] == e["id"] and not line["data"]["undone"]
    assert c["snapshot"]["to_collect"] == pytest.approx(before + 2500)
    app.post(f"/api/entries/{e['id']}/undo")
    c = app.get("/api/chat").json()
    assert c["items"][-1]["data"]["undone"] and c["snapshot"]["to_collect"] == pytest.approx(before)


def test_checkup_posts_into_the_thread_once_a_day_in_any_language(app):
    assert app.get("/api/chat").json()["checkup_due"]
    app.post("/api/agent/checkup")
    c = app.get("/api/chat").json()
    assert not c["checkup_due"] and c["items"][-1]["kind"] == "checkup" and c["items"][-1]["data"]["actions"]
    assert c["items"][-1]["data"]["answer"].startswith("**Namaste")
    assert not app.get("/api/chat", headers={"X-Lang": "hi"}).json()["checkup_due"]


def test_clearing_the_chat_keeps_the_khata(app):
    e = app.post("/api/entries", json={"kind": "sale", "amount": 700}).json()
    app.delete("/api/chat")
    assert app.get("/api/chat").json()["items"] == []
    assert any(r["id"] == e["id"] for r in app.get("/api/transactions?q=Walk-in").json()["rows"])
