"""The agentic Ask layer: shop tools, draft actions the owner confirms, the rule-based planner, live progress, AI key setup."""

import json
from types import SimpleNamespace as NS

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from finpilot import config
from finpilot.agent import offline, orchestrator
from finpilot.agent.orchestrator import run_ai, run_offline
from finpilot.agent.tools import ToolContext, run_tool
from finpilot.api.server import create_app

AS_OF = pd.Timestamp("2026-09-30")


@pytest.fixture
def ctx(demo, tmp_path):
    return ToolContext(demo["ledger"], demo["obligations"], demo["balances"], AS_OF, tmp_path / "t.db", "demo", "Demo Shop")


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("FINPILOT_AI", "off")
    monkeypatch.setenv("FINPILOT_ENV_FILE", str(tmp_path / "test.env"))
    from finpilot.api import dataset

    monkeypatch.setattr(dataset, "today", lambda: AS_OF)
    return TestClient(create_app(tmp_path / "t.db", static_dir=None))


# ---------------------------------------------------------------- shop tools


class TestShopTools:
    def test_khata_totals_match_the_invoices(self, ctx, demo):
        ok, r = run_tool(ctx, "get_customers_and_suppliers", {"side": "customers", "limit": 30})
        o = demo["obligations"]
        pend = o[(o["kind"] == "receivable") & (o["status"] == "pending")]
        assert ok and r["total_outstanding"] == pytest.approx(pend["amount"].sum())
        assert sum(p["outstanding"] for p in r["people"]) == pytest.approx(r["total_outstanding"])
        overdue = pend[pd.to_datetime(pend["due_date"]) < AS_OF]
        assert r["total_overdue"] == pytest.approx(overdue["amount"].sum())
        assert r["people"][0]["overdue"] == max(p["overdue"] for p in r["people"])  # sorted by overdue

    def test_best_customers_are_sorted_by_money_received(self, ctx):
        ok, r = run_tool(ctx, "get_customers_and_suppliers", {"sort_by": "paid", "limit": 5})
        paid = [p["paid_in_period"] for p in r["people"]]
        assert paid == sorted(paid, reverse=True) and paid[0] > 0

    def test_person_matches_a_partial_name(self, ctx):
        ok, r = run_tool(ctx, "get_person_details", {"name": "metro"})
        assert r["status"] == "ok" and r["name"] == "Metro Foods Pvt Ltd" and r["type"] == "customer"
        assert r["outstanding"] == pytest.approx(sum(i["amount"] for i in r["open_items"]))
        ok, r = run_tool(ctx, "get_person_details", {"name": "nobody at all"})
        assert r["status"] == "not_found"

    def test_health_score_is_the_sum_of_its_parts(self, ctx):
        ok, h = run_tool(ctx, "get_health_score", {})
        assert ok and h["score"] == round(sum(c["points"] for c in h["components"]))
        assert len(h["components"]) == 5

    def test_loan_what_if_never_assumes_terms(self, ctx):
        ok, r = run_tool(ctx, "run_what_if", {"kind": "loan", "loan_amount": 500000})
        assert r["status"] == "needs_input" and set(r["missing"]) == {"interest_rate_pct", "years"}

    def test_price_what_if_arithmetic(self, ctx):
        ok, r = run_tool(ctx, "run_what_if", {"kind": "price", "price_change_pct": 5})
        assert r["monthly_change"] == pytest.approx(r["new_profit"] - r["baseline"]["profit"], abs=0.01)

    def test_gst_estimate_respects_registration(self, ctx):
        from finpilot.data import books

        ok, r = run_tool(ctx, "get_tax_calendar_and_gst", {})
        assert r["gst_registered"] and "gst_last_full_month" in r and r["upcoming_due_dates"]
        books.set_settings(ctx.db_path, "demo", {"gst_registered": "no"})
        ok, r = run_tool(ctx, "get_tax_calendar_and_gst", {})
        assert not r["gst_registered"] and "gst_last_full_month" not in r


class TestDrafts:
    def test_draft_entry_is_checked_but_not_saved(self, ctx):
        before = len(ctx.ledger)
        ok, r = run_tool(ctx, "draft_entry", {"kind": "payment_in", "amount": 70000, "party": "Metro Foods"})
        assert r["status"] == "needs_confirmation" and r["action"] == "record_entry"
        assert r["payload"]["party"] == "Metro Foods Pvt Ltd"  # matched to the known name
        assert r["preview"]["would_settle"][0]["id"] == "INV-0099"  # oldest due first
        assert len(ctx.ledger) == before

    def test_draft_entry_rejects_bad_input(self, ctx):
        ok, r = run_tool(ctx, "draft_entry", {"kind": "credit_sale", "amount": 500})
        assert r["status"] == "invalid" and "name" in r["message"].lower()
        ok, r = run_tool(ctx, "draft_entry", {"kind": "sale", "amount": 500, "date": "2027-01-01"})
        assert r["status"] == "invalid"
        ok, r = run_tool(ctx, "draft_entry", {"kind": "steal", "amount": 5})
        assert not ok

    def test_reminder_only_for_overdue_dues(self, ctx):
        ok, r = run_tool(ctx, "draft_reminder", {"customer": "Metro Foods"})
        assert r["status"] == "needs_confirmation" and "wa.me" in r["payload"]["whatsapp"] and "INV-0099" in r["payload"]["text"]
        ok, r = run_tool(ctx, "draft_reminder", {"customer": "Kumar Wholesale"})
        assert r["status"] == "nothing_overdue"

    def test_goal_and_budget_drafts(self, ctx):
        ok, g = run_tool(ctx, "draft_goal", {"name": "Fridge", "target": 60000, "target_date": "2027-03-31"})
        assert g["status"] == "needs_confirmation" and g["preview"]["per_month"] == 10000 and g["preview"]["months_left"] == 6
        ok, b = run_tool(ctx, "draft_budget", {"category": "rent", "monthly_limit": 50000})
        assert b["payload"]["category"] == "Rent" and b["preview"]["spent_this_month"] == 55000
        ok, b = run_tool(ctx, "draft_budget", {"category": "spaceships", "monthly_limit": 5})
        assert b["status"] == "invalid"


# ---------------------------------------------------------------- rule-based planner


def tools_for(q, ctx, lang="en"):
    return [s.tool for s in run_offline(q, ctx, lang=lang).steps]


class TestPlanner:
    @pytest.mark.parametrize("q,tool", [
        ("who is my best customer?", "get_customers_and_suppliers"),
        ("which customers pay late?", "get_customers_and_suppliers"),
        ("what is my health score", "get_health_score"),
        ("how did this week go?", "get_weekly_story"),
        ("can I raise prices by 5%?", "run_what_if"),
        ("should I hire a helper for 15000?", "run_what_if"),
        ("how much GST should I keep aside?", "get_tax_calendar_and_gst"),
        ("how much does Metro owe me?", "get_person_details"),
        ("is my rent too high?", "get_financial_summary"),
        ("am I making money?", "get_financial_summary"),
    ])
    def test_everyday_questions_reach_a_tool_and_verify(self, ctx, q, tool):
        run = run_offline(q, ctx)
        assert tool in [s.tool for s in run.steps], run.answer
        assert run.verified, (run.warnings, run.answer)

    def test_briefing_looks_broadly_and_drafts_one_reminder(self, ctx):
        run = run_offline("What should I do today?", ctx)
        tools = [s.tool for s in run.steps]
        assert {"get_customers_and_suppliers", "get_upcoming_payments", "get_health_score", "get_cash_position"} <= set(tools)
        assert {a["action"] for a in run.actions} == {"send_reminder"} and run.plan and all(st["status"] == "done" for st in run.plan)
        assert run.verified and "Metro Foods" in run.answer

    def test_two_part_question_runs_both(self, ctx):
        tools = tools_for("give me a summary and tell me who owes me", ctx)
        assert "get_financial_summary" in tools and "get_receivables_and_payables" in tools

    @pytest.mark.parametrize("q,kind", [("add a sale of 500 cash", "sale"), ("received 20000 from Kumar Wholesale", "payment_in"),
                                        ("Ramesh ko 2000 udhaar", "credit_sale"), ("paid rent 55000", "expense"), ("kal 5000 ka maal becha", "sale")])
    def test_entries_become_drafts(self, ctx, q, kind):
        run = run_offline(q, ctx)
        assert [a["action"] for a in run.actions] == ["record_entry"] and run.actions[0]["payload"]["kind"] == kind

    @pytest.mark.parametrize("q", ["how are sales trending?", "who did I sell the most to?", "what did I spend on rent?"])
    def test_questions_are_not_mistaken_for_entries(self, ctx, q):
        assert not run_offline(q, ctx).actions

    def test_greeting_needs_no_tools(self, ctx):
        run = run_offline("hi", ctx)
        assert not run.steps and "Namaste" in run.answer

    def test_hindi_briefing(self, ctx):
        run = run_offline("आज मुझे क्या करना चाहिए?", ctx, lang="hi")
        assert run.actions and "वसूल" in run.answer and run.verified

    def test_purchase_beats_saving_words(self, ctx):
        assert "simulate_purchase" in tools_for("Can we afford a ₹12 lakh machine? It would save ₹45,000 a month.", ctx)

    def test_find_party(self):
        parties = ["Metro Foods Pvt Ltd", "Kumar Wholesale", "Shree Ganesh Traders"]
        assert offline._find_party("how much does metro owe", parties) == "Metro Foods Pvt Ltd"
        assert offline._find_party("what about Shree Ganesh Traders?", parties) == "Shree Ganesh Traders"
        assert offline._find_party("how much do traders owe", parties) is None


# ---------------------------------------------------------------- AI mode with a scripted model


def text(t):
    return NS(type="text", text=t)


def tool_use(i, name, args):
    return NS(type="tool_use", id=i, name=name, input=args)


class FakeClient:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []
        self.beta = NS(messages=NS(create=self._create))
        self.models = NS(list=lambda **kw: [])

    def _create(self, **kw):
        self.calls.append(kw)
        content, stop = self.script.pop(0)(kw["messages"])
        return NS(content=content, stop_reason=stop)


class TestAIMode:
    def test_notes_and_events_stream_and_drafts_surface(self, ctx):
        events = []
        client = FakeClient([
            lambda m: ([text("Checking who owes you and preparing a reminder."), tool_use("a", "get_customers_and_suppliers", {"limit": 3}),
                        tool_use("b", "draft_reminder", {"customer": "Metro Foods"})], "tool_use"),
            lambda m: ([text("**Metro Foods Pvt Ltd owes ₹2,94,000 overdue.** A reminder is ready below for you to confirm.")], "end_turn"),
        ])
        run = run_ai("who should I chase?", ctx, client, "m", "Demo", on_event=events.append)
        assert run.notes == ["Checking who owes you and preparing a reminder."]
        assert [e["type"] for e in events] == ["note", "tool_start", "tool_done", "tool_start", "tool_done"]
        assert run.actions and run.actions[0]["action"] == "send_reminder"
        assert run.verified, run.warnings

    def test_prompt_lists_draft_tools_and_preface_is_sent(self, ctx):
        client = FakeClient([lambda m: ([text("Hello! I can check your cash.")], "end_turn")])
        run_ai("hi", ctx, client, "m", "Demo", preface="[App note] The owner confirmed a sale.")
        kw = client.calls[0]
        names = {t["name"] for t in kw["tools"]}
        assert {"draft_entry", "draft_reminder", "draft_goal", "draft_budget", "get_health_score"} <= names
        assert "draft_entry" in kw["system"] and kw["messages"][0]["content"].startswith("[App note]")

    def test_api_error_falls_back_with_a_plain_reason(self, ctx):
        class Boom:
            beta = NS(messages=NS(create=lambda **kw: (_ for _ in ()).throw(type("AuthenticationError", (Exception,), {})("no"))))

        s = NS(ai_enabled=True, anthropic_api_key="sk-ant-x", model="m", max_agent_steps=4)
        run = orchestrator.ask("who owes me?", ctx, "Demo", s, client=Boom())
        assert run.mode == "rule-based" and "not accepted" in run.warnings[0]


# ---------------------------------------------------------------- API: confirm, stream, key setup


class TestAskAPI:
    def test_confirming_a_drafted_entry_saves_it_once(self, app_client):
        r = app_client.post("/api/ask", json={"question": "add a sale of 500 cash"}).json()
        assert r["actions"] and r["actions"][0]["kind"] == "record_entry" and r["suggestions"]
        cid, aid = r["conversation_id"], r["actions"][0]["id"]
        before = app_client.get("/api/transactions?q=Walk-in").json()["total"]
        ok = app_client.post(f"/api/ask/action/{aid}", json={"conversation_id": cid, "decision": "confirm"})
        assert ok.status_code == 200 and ok.json()["id"].startswith("E")
        assert app_client.get("/api/transactions?q=Walk-in").json()["total"] == before + 1
        again = app_client.post(f"/api/ask/action/{aid}", json={"conversation_id": cid, "decision": "confirm"})
        assert again.status_code == 409
        assert app_client.post("/api/ask/action/nope", json={"conversation_id": cid}).status_code == 404

    def test_cancel_and_goal_budget_reminder(self, app_client):
        r = app_client.post("/api/ask", json={"question": "set a rent budget of ₹50,000"}).json()
        cid, aid = r["conversation_id"], r["actions"][0]["id"]
        assert app_client.post(f"/api/ask/action/{aid}", json={"conversation_id": cid, "decision": "cancel"}).json()["state"] == "cancelled"
        assert app_client.get("/api/budgets").json()["limits"] == {}
        r = app_client.post("/api/ask", json={"question": "set a rent budget of ₹50,000", "conversation_id": cid}).json()
        app_client.post(f"/api/ask/action/{r['actions'][0]['id']}", json={"conversation_id": cid, "decision": "confirm"})
        assert app_client.get("/api/budgets").json()["limits"] == {"Rent": 50000}
        r = app_client.post("/api/ask", json={"question": "save ₹60,000 for a fridge by March", "conversation_id": cid}).json()
        app_client.post(f"/api/ask/action/{r['actions'][0]['id']}", json={"conversation_id": cid, "decision": "confirm"})
        assert app_client.get("/api/goals").json()[0]["target"] == 60000
        r = app_client.post("/api/ask", json={"question": "remind Metro Foods", "conversation_id": cid}).json()
        a = r["actions"][0]
        assert a["kind"] == "send_reminder" and "wa.me" in a["whatsapp"] and a["text"]
        out = app_client.post(f"/api/ask/action/{a['id']}", json={"conversation_id": cid, "decision": "confirm"}).json()
        assert out["open"].startswith("https://wa.me/")

    def test_stream_sends_progress_then_the_answer(self, app_client):
        with app_client.stream("POST", "/api/ask/stream", json={"question": "What should I do today?"}) as resp:
            events = [json.loads(line[6:]) for line in resp.iter_lines() if line.startswith("data: ")]
        kinds = [e["type"] for e in events]
        assert kinds[0] == "start" and kinds[-1] == "final" and "tool_start" in kinds and "tool_done" in kinds
        assert all(e.get("label") for e in events if e["type"] == "tool_start")
        final = events[-1]["data"]
        done = [e for e in events if e["type"] == "tool_done" and e["tool"] != "update_plan"]
        assert final["verified"] and final["actions"] and len(final["steps"]) == len(done) and "plan" in kinds and final["plan"]

    def test_stream_in_hindi(self, app_client):
        with app_client.stream("POST", "/api/ask/stream", json={"question": "किस पर उधारी बाकी है?"}, headers={"X-Lang": "hi"}) as resp:
            events = [json.loads(line[6:]) for line in resp.iter_lines() if line.startswith("data: ")]
        assert events[-1]["data"]["steps"][0]["label"] == "उधारी और बकाया जाँचा"


class TestAIKey:
    def test_key_setup_needs_consent_checks_and_saves_locally(self, app_client, tmp_path, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "")
        assert app_client.get("/api/ai").json()["has_key"] is False
        assert app_client.post("/api/ai/key", json={"key": "sk-ant-api03-abcdefghijklmnopqrstuv"}).status_code == 400  # no consent
        assert app_client.post("/api/ai/key", json={"key": "hello", "consent": True}).status_code == 400
        monkeypatch.setattr(orchestrator, "check_key", lambda k, lang="en": (False, "the API key was not accepted"))
        bad = app_client.post("/api/ai/key", json={"key": "sk-ant-api03-abcdefghijklmnopqrstuv", "consent": True})
        assert bad.status_code == 400 and "not accepted" in bad.json()["detail"]
        monkeypatch.setattr(orchestrator, "check_key", lambda k, lang="en": (True, ""))
        try:
            s = app_client.post("/api/ai/key", json={"key": "sk-ant-api03-abcdefghijklmnopqrstuv", "consent": True}).json()
            assert s["enabled"] and s["key_hint"] == "…stuv" and s["source"] == "app"
            assert "sk-ant-api03-abcdefghijklmnopqrstuv" in (tmp_path / "test.env").read_text()
            assert "abcdefghijklmnop" not in json.dumps(app_client.get("/api/state").json())  # never echoed back
            assert app_client.post("/api/ai/pause", json={"paused": True}).json()["enabled"] is False
            assert app_client.post("/api/ai/pause", json={"paused": False}).json()["enabled"] is True
        finally:
            s = app_client.delete("/api/ai/key").json()
        assert not s["has_key"] and "sk-ant" not in (tmp_path / "test.env").read_text()

    def test_env_file_helpers_keep_other_lines(self, tmp_path, monkeypatch):
        f = tmp_path / "x.env"
        f.write_text("# comment\nFINPILOT_MODEL=abc\n")
        monkeypatch.setenv("FINPILOT_ENV_FILE", str(f))
        config.save_local("FOO_TEST_VAR", "1")
        config.save_local("FOO_TEST_VAR", "2")
        assert config.local_env() == {"FINPILOT_MODEL": "abc", "FOO_TEST_VAR": "2"}
        config.save_local("FOO_TEST_VAR", None)
        assert "FOO_TEST_VAR" not in f.read_text() and "# comment" in f.read_text()
