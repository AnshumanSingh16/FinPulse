"""The proactive agent: daily check-up with a plan, persistent action inbox, approve-all, memory that changes behaviour, promises."""

import json
from types import SimpleNamespace as NS

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from finpilot.agent import orchestrator
from finpilot.agent.tools import ToolContext, run_tool
from finpilot.api.server import create_app
from finpilot.data import books

AS_OF = pd.Timestamp("2026-09-30")


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("FINPILOT_AI", "off")
    monkeypatch.setenv("FINPILOT_ENV_FILE", str(tmp_path / "test.env"))
    from finpilot.api import dataset

    monkeypatch.setattr(dataset, "today", lambda: AS_OF)
    return tmp_path / "t.db"


@pytest.fixture
def app(env):
    return TestClient(create_app(env, static_dir=None))


class TestCheckup:
    def test_runs_once_a_day_with_a_finished_plan_and_saved_actions(self, app):
        s = app.get("/api/agent").json()
        assert s["stale"] and s["checkup"] is None
        c = app.post("/api/agent/checkup").json()
        assert c["plan"] and all(st["status"] == "done" for st in c["plan"]) and c["verified"]
        assert c["actions"] and all(a["state"] == "pending" for a in c["actions"])
        assert all(st["tool"] != "update_plan" for st in c["steps"])
        s = app.get("/api/agent").json()
        assert not s["stale"] and s["checkup"]["answer"] == c["answer"] and s["pending"] == len(c["actions"])

    def test_stream_shows_the_plan_ticking(self, app):
        with app.stream("POST", "/api/agent/checkup/stream") as r:
            ev = [json.loads(line[6:]) for line in r.iter_lines() if line.startswith("data: ")]
        plans = [e["steps"] for e in ev if e["type"] == "plan"]
        assert len(plans) >= 5 and plans[0][0]["status"] == "doing" and all(st["status"] == "done" for st in plans[-1])
        assert ev[-1]["type"] == "final" and ev[-1]["data"]["actions"]

    def test_a_new_checkup_expires_yesterdays_pending_cards(self, app, env):
        first = app.post("/api/agent/checkup").json()["actions"]
        app.post("/api/agent/checkup")
        old = books.get_action(env, "demo", first[0]["id"])
        assert old["state"] == "expired"
        assert app.post(f"/api/agent/actions/{first[0]['id']}", json={}).status_code == 404


class TestInbox:
    def test_actions_survive_a_restart_and_approve_all_skips_reminders(self, app, env):
        cid = app.post("/api/ask", json={"question": "set a rent budget of ₹50,000"}).json()["conversation_id"]
        g = app.post("/api/ask", json={"question": "save ₹60,000 for a fridge by March", "conversation_id": cid}).json()
        r = app.post("/api/ask", json={"question": "remind Metro Foods", "conversation_id": cid}).json()
        ids = [a["id"] for a in books.actions(env, "demo", state="pending")]
        assert len(ids) == 3 and g["actions"][0]["id"] in ids
        fresh = TestClient(create_app(env, static_dir=None))  # new server process, same database
        out = fresh.post("/api/agent/approve-all", json={"ids": ids}).json()
        assert out["done"] == 2
        assert fresh.get("/api/budgets").json()["limits"] == {"Rent": 50000} and fresh.get("/api/goals").json()[0]["target"] == 60000
        rem = books.get_action(env, "demo", r["actions"][0]["id"])
        assert rem["state"] == "pending"  # a reminder is opened one by one by the owner
        assert fresh.post(f"/api/agent/actions/{rem['id']}", json={"decision": "confirm"}).json()["open"].startswith("https://wa.me/")

    def test_promise_and_recategorise_drafts_confirm(self, app, env, demo, monkeypatch):
        r = app.post("/api/ask", json={"question": "Shree Ganesh promised to pay 89000 by 10 Oct"}).json()
        a = r["actions"][0]
        assert a["kind"] == "record_promise"
        app.post(f"/api/agent/actions/{a['id']}", json={"decision": "confirm"})
        assert books.promises(env, "demo")[0]["party"] == "Shree Ganesh Traders"
        # a guessed category, confirmed through a drafted fix
        from finpilot.api import dataset

        d = dataset.current(env)
        lg = d.ledger.copy()
        lg.loc[lg["counterparty"] == "Metro Foods Pvt Ltd", "reference"] = "auto:guess"
        from finpilot.data import khata

        dataset.save(env, d, khata.Tables(lg, d.obligations, d.balances))
        ctx = ToolContext(lg, d.obligations, d.balances, AS_OF, env, "demo", "Demo")
        ok, res = run_tool(ctx, "draft_recategorise", {"party": "Metro", "category": "sales - b2b"})
        metro = int((lg["counterparty"] == "Metro Foods Pvt Ltd").sum())
        assert res["status"] == "needs_confirmation" and res["payload"]["category"] == "Sales - B2B" and res["preview"]["count"] == metro > 0
        books.save_action(env, "demo", "chat", res)
        assert app.post(f"/api/agent/actions/{res['action_id']}", json={}).json()["state"] == "done"
        assert not dataset.current(env).ledger.loc[lambda x: x["counterparty"] == "Metro Foods Pvt Ltd", "reference"].astype(str).str.contains("auto:guess").any()


class TestMemory:
    def test_memory_changes_what_the_agent_prepares(self, app):
        app.post("/api/ask", json={"question": "never remind Metro Foods, they are my oldest client"})
        mem = app.get("/api/agent/memory").json()
        assert len(mem) == 1 and "Metro" in mem[0]["text"]
        r = app.post("/api/ask", json={"question": "help me collect my money"}).json()
        assert [a["title"] for a in r["actions"]] == ["WhatsApp reminder to Shree Ganesh Traders"] and r["plan"]
        assert "Skipped a reminder to Metro Foods" in r["answer"]
        app.delete(f"/api/agent/memory/{mem[0]['id']}")
        r = app.post("/api/ask", json={"question": "help me collect my money"}).json()
        assert len(r["actions"]) == 2

    def test_memory_reaches_the_ai_prompt(self, demo, tmp_path):
        db = tmp_path / "m.db"
        books.add_memory(db, "demo", "I close on Sundays")
        ctx = ToolContext(demo["ledger"], demo["obligations"], demo["balances"], AS_OF, db, "demo", "Demo")
        assert "#1: I close on Sundays" in orchestrator.system_prompt(ctx, "Demo")


class TestAICheckup:
    def test_ai_checkup_plans_and_drafts(self, demo, tmp_path):
        calls = []

        def create(**kw):
            calls.append(kw)
            n = len(calls)
            if n == 1:
                return NS(content=[NS(type="text", text="Starting the check-up."),
                                   NS(type="tool_use", id="p", name="update_plan", input={"steps": [{"title": "Check dues", "status": "doing"}]}),
                                   NS(type="tool_use", id="a", name="get_customers_and_suppliers", input={})], stop_reason="tool_use")
            if n == 2:
                return NS(content=[NS(type="tool_use", id="b", name="draft_reminder", input={"customer": "Metro Foods"}),
                                   NS(type="tool_use", id="c", name="update_plan", input={"steps": [{"title": "Check dues", "status": "done"}]})], stop_reason="tool_use")
            return NS(content=[NS(type="text", text="**One thing today:** collect ₹2,94,000 from Metro Foods Pvt Ltd — a reminder is ready.")], stop_reason="end_turn")

        client = NS(beta=NS(messages=NS(create=create)))
        ctx = ToolContext(demo["ledger"], demo["obligations"], demo["balances"], AS_OF, tmp_path / "a.db", "demo", "Demo")
        events = []
        s = NS(ai_enabled=True, provider="anthropic", anthropic_api_key="k", model="m", max_agent_steps=8)
        run = orchestrator.checkup(ctx, "Demo", s, client=client, on_event=events.append)
        assert calls[0]["messages"][0]["content"].startswith("[Daily check-up")
        assert run.plan == [{"title": "Check dues", "status": "done"}] and run.actions and run.verified
        assert [e["type"] for e in events].count("plan") == 2
