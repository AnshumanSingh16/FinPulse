"""Gemini as the agent's model: request shape, the tool loop, drafts, verification, key check and setup — with a scripted fake, no network."""

import json
from types import SimpleNamespace as NS

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from finpilot.agent import gemini, orchestrator
from finpilot.agent.tools import ToolContext
from finpilot.api.server import create_app

AS_OF = pd.Timestamp("2026-09-30")


@pytest.fixture
def ctx(demo, tmp_path):
    return ToolContext(demo["ledger"], demo["obligations"], demo["balances"], AS_OF, tmp_path / "t.db", "demo", "Demo Shop")


class FakeGemini:
    """Replays scripted generateContent responses; each item is a function(body) -> response dict."""

    def __init__(self, script):
        self.script, self.calls = list(script), []

    def __call__(self, path, body, api_key):
        self.calls.append((path, json.loads(json.dumps(body)), api_key))
        return self.script.pop(0)(body)


def reply(*parts, finish="STOP"):
    return {"candidates": [{"content": {"role": "model", "parts": list(parts)}, "finishReason": finish}]}


def call(name, args, sig=None):
    p = {"functionCall": {"name": name, "args": args}}
    if sig:
        p["thoughtSignature"] = sig
    return p


def last_response(body, name):
    return next(p["functionResponse"]["response"] for p in body["contents"][-1]["parts"] if p.get("functionResponse", {}).get("name") == name)


class TestDeclarations:
    def test_every_tool_is_declared_in_geminis_schema_subset(self):
        decls = gemini.function_declarations()
        assert len(decls) == 33
        blob = json.dumps(decls)
        assert "additionalProperties" not in blob and '"object"' not in blob
        sim = next(d for d in decls if d["name"] == "simulate_purchase")
        assert sim["parameters"]["type"] == "OBJECT" and set(sim["parameters"]["required"]) == {"name", "cost"}
        assert "parameters" not in next(d for d in decls if d["name"] == "get_health_score")  # no-argument tool
        prop = next(d for d in decls if d["name"] == "propose_action")["parameters"]["properties"]
        assert "details" not in prop  # free-form object dropped (optional)


class TestLoop:
    def test_tools_run_answer_verifies_and_signatures_round_trip(self, ctx):
        events = []

        def answer(body):
            cash = last_response(body, "get_cash_position")["cash_balance"]
            return reply({"text": f"**You have ₹{cash:,.0f} in the bank on 30 Sep 2026.**".replace("₹1,485,414", "₹14,85,414")})

        fake = FakeGemini([lambda b: reply({"text": "Checking your bank balance."}, call("get_cash_position", {}, sig="abc")), answer])
        run = gemini.run_gemini("How much cash?", ctx, "AIza-test", "gemini-x", "Demo", post=fake, on_event=events.append)
        assert [s.tool for s in run.steps] == ["get_cash_position"] and run.verified, run.warnings
        assert run.notes == ["Checking your bank balance."] and [e["type"] for e in events] == ["note", "tool_start", "tool_done"]
        path, body, key = fake.calls[1]
        assert path == "models/gemini-x:generateContent" and key == "AIza-test"
        assert body["contents"][1]["parts"][1]["thoughtSignature"] == "abc"  # model turn kept verbatim
        assert "FinPilot" in body["systemInstruction"]["parts"][0]["text"]

    def test_invented_figure_gets_one_repair_then_a_warning(self, ctx):
        fake = FakeGemini([
            lambda b: reply(call("get_cash_position", {})),
            lambda b: reply({"text": "You have ₹20,00,000."}),
            lambda b: reply({"text": "You have ₹99,99,999."}),
        ])
        run = gemini.run_gemini("cash?", ctx, "k", "m", "Demo", post=fake)
        assert run.repaired and not run.verified and any("₹99,99,999" in w for w in run.warnings)
        assert "Automatic verification" in fake.calls[2][1]["contents"][-1]["parts"][0]["text"]

    def test_drafts_surface_as_confirm_cards(self, ctx):
        fake = FakeGemini([
            lambda b: reply(call("draft_entry", {"kind": "sale", "amount": 500})),
            lambda b: reply({"text": "A sale of ₹500 is ready below — tap Confirm to save it."}),
        ])
        run = gemini.run_gemini("add a sale of 500", ctx, "k", "m", "Demo", post=fake)
        assert run.actions and run.actions[0]["action"] == "record_entry" and run.verified

    def test_step_limit_forces_an_answer(self, ctx):
        script = [lambda b: reply(call("get_health_score", {})) for _ in range(2)] + [lambda b: reply({"text": "Here is what I found."})]
        fake = FakeGemini(script)
        run = gemini.run_gemini("q", ctx, "k", "m", "Demo", max_steps=2, post=fake)
        assert fake.calls[2][1]["toolConfig"]["functionCallingConfig"]["mode"] == "NONE"
        assert any("Stopped after 2" in w for w in run.warnings)

    def test_blocked_prompt_is_reported(self, ctx):
        run = gemini.run_gemini("q", ctx, "k", "m", "Demo", post=FakeGemini([lambda b: {"promptFeedback": {"blockReason": "SAFETY"}}]))
        assert "declined" in run.answer and run.warnings


class TestKeyAndModels:
    def test_pick_model_prefers_default_then_newest_flash(self):
        ms = lambda *n: [{"name": f"models/{x}", "supportedGenerationMethods": ["generateContent"]} for x in n]  # noqa: E731
        assert gemini.pick_model(ms("gemini-2.5-flash", "gemini-3-flash")) == "gemini-2.5-flash"
        assert gemini.pick_model(ms("gemini-2.0-flash", "gemini-3.1-flash", "gemini-3-pro")) == "gemini-3.1-flash"
        assert gemini.pick_model([{"name": "models/embedding-001", "supportedGenerationMethods": ["embedContent"]}]) is None

    def test_errors_map_to_plain_reasons(self, ctx):
        bad = {"error": {"message": "API key not valid.", "details": [{"reason": "API_KEY_INVALID"}]}}
        with pytest.raises(gemini.AuthenticationError):
            gemini._raise_for(400, bad)
        with pytest.raises(gemini.RateLimitError):
            gemini._raise_for(429, {})
        assert orchestrator._why(gemini.RateLimitError("x")).startswith("the free/rate limit")

        def boom(*a):
            raise gemini.RateLimitError("quota")

        s = NS(ai_enabled=True, provider="gemini", api_key="AIza-x", active_model="m", anthropic_api_key=None, model="c", max_agent_steps=4)
        run = orchestrator.ask("who owes me?", ctx, "Demo", s, client=boom)
        assert run.mode == "rule-based" and "limit" in run.warnings[0] and run.steps


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("FINPILOT_AI", "off")
    monkeypatch.setenv("FINPILOT_ENV_FILE", str(tmp_path / "test.env"))
    for v in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "FINPILOT_PROVIDER", "FINPILOT_GEMINI_MODEL"):
        monkeypatch.setenv(v, "")
    from finpilot.api import dataset

    monkeypatch.setattr(dataset, "today", lambda: AS_OF)
    return TestClient(create_app(tmp_path / "t.db", static_dir=None))


class TestSetup:
    def test_gemini_key_setup_and_ask_through_gemini(self, app_client, tmp_path, monkeypatch):
        key = "AIzaSyTestTestTestTestTestTestTestTest1234"
        assert app_client.post("/api/ai/key", json={"key": key, "provider": "gemini"}).status_code == 400  # consent
        assert app_client.post("/api/ai/key", json={"key": "sk-ant-api03-abcdefghijklmnopqrstuv", "provider": "gemini", "consent": True}).status_code == 400
        monkeypatch.setattr(orchestrator, "check_gemini_key", lambda k, lang="en", preferred=None: (True, "", "gemini-3-flash"))
        try:
            s = app_client.post("/api/ai/key", json={"key": key, "consent": True}).json()  # provider detected from the key
            assert s["enabled"] and s["provider"] == "gemini" and s["model"] == "gemini-3-flash" and s["key_hint"] == "…1234"
            env = (tmp_path / "test.env").read_text()
            assert key in env and "FINPILOT_PROVIDER=gemini" in env
            assert key not in json.dumps(app_client.get("/api/state").json())

            seen = {}

            def fake_post(path, body, api_key):
                seen["path"], seen["key"] = path, api_key
                if len(body["contents"]) == 1:
                    return reply({"text": "Checking who owes you."}, call("get_receivables_and_payables", {}))
                owed = last_response(body, "get_receivables_and_payables")["receivables"]["outstanding"]
                return reply({"text": f"**Customers owe you ₹{owed:,.0f}.**".replace("₹1,079,000", "₹10,79,000")})

            monkeypatch.setattr(gemini, "http_post", fake_post)
            r = app_client.post("/api/ask", json={"question": "who owes me?"}).json()
            assert r["mode"] == "ai" and r["verified"] and "₹10,79,000" in r["answer"] and r["notes"] == ["Checking who owes you."]
            assert seen == {"path": "models/gemini-3-flash:generateContent", "key": key}
        finally:
            s = app_client.delete("/api/ai/key").json()
        assert not s["has_key"] and key not in (tmp_path / "test.env").read_text()

    def test_bad_gemini_key_is_refused_with_a_reason(self, app_client, monkeypatch):
        monkeypatch.setattr(orchestrator, "check_gemini_key", lambda k, lang="en", preferred=None: (False, "the API key was not accepted", None))
        r = app_client.post("/api/ai/key", json={"key": "AIzaSyTestTestTestTestTestTestTestTest1234", "consent": True})
        assert r.status_code == 400 and "not accepted" in r.json()["detail"]

    def test_newer_aq_gemini_keys_are_accepted(self, app_client, monkeypatch):
        # Google AI Studio now also issues keys starting with "AQ."; the live check decides, not the prefix
        checked = []
        monkeypatch.setattr(orchestrator, "check_gemini_key", lambda k, lang="en", preferred=None: (checked.append(k) or True, "", "gemini-2.5-flash"))
        key = "AQ.TestTestTestTestTestTestTestTestTest"
        try:
            s = app_client.post("/api/ai/key", json={"key": key, "consent": True}).json()
            assert checked == [key] and s["enabled"] and s["provider"] == "gemini"
        finally:
            app_client.delete("/api/ai/key")
