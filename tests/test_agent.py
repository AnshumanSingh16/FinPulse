"""Agent layer: tool validation, independent verification, the orchestration loop (with a scripted
fake model, so no network or API key is used) and the rule-based mode."""

from types import SimpleNamespace as NS

import pandas as pd
import pytest

from finpilot.agent import orchestrator
from finpilot.agent.orchestrator import run_ai, run_offline
from finpilot.agent.tools import TOOLS, ToolContext, anthropic_tool_specs, run_tool
from finpilot.agent.verify import check_tool_result, verify_answer
from finpilot.data import store

AS_OF = pd.Timestamp("2026-09-30")


@pytest.fixture
def ctx(demo, tmp_path):
    return ToolContext(demo["ledger"], demo["obligations"], demo["balances"], AS_OF, tmp_path / "t.db")


@pytest.fixture
def tiny_ctx(tiny):
    return ToolContext(tiny["ledger"], tiny["obligations"], tiny["balances"], tiny["as_of"], None)


# ---------------------------------------------------------------- tools


class TestTools:
    def test_specs_are_well_formed(self):
        specs = anthropic_tool_specs()
        assert {s["name"] for s in specs} >= {
            "get_financial_summary", "analyze_expense_changes", "get_cash_position", "get_upcoming_payments",
            "forecast_cash_flow", "simulate_purchase", "get_supporting_records",
        }
        for s in specs:
            assert s["input_schema"]["type"] == "object" and s["input_schema"]["additionalProperties"] is False

    @pytest.mark.parametrize(
        "name,args,fragment",
        [
            ("get_financial_summary", {"start_date": "01/04/2026"}, "YYYY-MM-DD"),
            ("get_financial_summary", {"start_date": "2026-02-30"}, "not a real date"),
            ("get_financial_summary", {"profit": 5}, "Unknown argument"),
            ("forecast_cash_flow", {"horizon_days": 5000}, "between"),
            ("forecast_cash_flow", {"horizon_days": "90"}, "number"),
            ("simulate_purchase", {"name": "Van"}, "'cost' is required"),
            ("simulate_purchase", {"name": "Van", "cost": 1e5, "financing": "lease"}, "one of"),
            ("analyze_expense_changes", {"period_a_start": "2026-01-01"}, "all four"),
            ("get_cash_position", {"as_of_date": "2027-01-01"}, "future"),
            ("get_supporting_records", {"record_ids": []}, "non-empty"),
        ],
    )
    def test_invalid_arguments_are_rejected_before_running(self, ctx, name, args, fragment):
        ok, r = run_tool(ctx, name, args)
        assert not ok and r["status"] == "invalid_arguments" and fragment in r["message"]

    def test_unknown_tool(self, ctx):
        ok, r = run_tool(ctx, "transfer_money", {})
        assert not ok and "Unknown tool" in r["message"]

    def test_loan_without_rate_asks_instead_of_assuming(self, ctx):
        ok, r = run_tool(ctx, "simulate_purchase", {"name": "Van", "cost": 800000, "financing": "loan"})
        assert ok and r["status"] == "needs_input" and set(r["missing"]) == {"loan_rate_pct", "tenure_months"}

    def test_cash_purchase_runs(self, ctx):
        ok, r = run_tool(ctx, "simulate_purchase", {"name": "Oven", "cost": 300000, "financing": "cash"})
        assert ok and r["status"] == "ok" and r["emi"] in (0, None)
        assert all("daily_with" not in s for s in r["scenarios"])  # trimmed for the model

    def test_results_are_trimmed_but_keep_evidence(self, ctx):
        ok, r = run_tool(ctx, "get_financial_summary", {})
        ev = r["evidence"]
        assert len(ev["record_ids"]) <= 25 and ev["record_count"] > 25 and ev["method"]
        ok, f = run_tool(ctx, "forecast_cash_flow", {"horizon_days": 90})
        assert "daily" not in f and f["scheduled_items_count"] > 0
        assert [c["days"] for c in f["checkpoints"]][:3] == [30, 60, 90]

    def test_receivables_outstanding(self, tiny_ctx):
        ok, r = run_tool(tiny_ctx, "get_receivables_and_payables", {})
        assert r["receivables"]["outstanding"] == 65_000  # 40k overdue + 25k not yet due
        assert r["payables"]["outstanding"] == 35_000

    def test_supporting_records_reports_missing(self, ctx):
        ok, r = run_tool(ctx, "get_supporting_records", {"record_ids": ["T0012", "T9999", "INV-0050"]})
        assert [t["txn_id"] for t in r["transactions"]] == ["T0012"]
        assert [b["item_id"] for b in r["invoices_and_bills"]] == ["INV-0050"]
        assert r["not_found"] == ["T9999"]

    def test_propose_action_only_queues(self, ctx):
        ok, r = run_tool(ctx, "propose_action", {"action": "Send payment reminder to Metro Foods", "reason": "4 invoices overdue"})
        assert r["status"] == "awaiting_human_approval"
        q = store.approvals(ctx.db_path)
        assert len(q) == 1 and q[0]["status"] == "pending"

    def test_every_tool_runs_on_demo_without_error(self, ctx):
        minimal = {"simulate_purchase": {"name": "x", "cost": 100000}, "get_supporting_records": {"record_ids": ["T0001"]},
                   "propose_action": {"action": "a", "reason": "b"}, "get_person_details": {"name": "Metro"},
                   "run_what_if": {"kind": "price", "price_change_pct": 5}, "draft_entry": {"kind": "sale", "amount": 500},
                   "draft_reminder": {"customer": "Metro Foods"}, "draft_goal": {"name": "Fridge", "target": 60000},
                   "draft_budget": {"category": "Rent", "monthly_limit": 50000},
                   "update_plan": {"steps": [{"title": "Check cash", "status": "doing"}]}, "remember": {"fact": "Closed on Sundays"},
                   "forget": {"id": 1}, "draft_promise": {"customer": "Metro Foods", "date": "2026-10-10"},
                   "draft_recategorise": {"party": "Metro Foods", "category": "Sales"}, "plan_purchase": {"amount": 300000, "label": "Machine"}}
        for t in TOOLS:
            ok, r = run_tool(ctx, t.name, minimal.get(t.name, {}))
            assert ok, (t.name, r)


# ---------------------------------------------------------------- verification


class TestVerification:
    def test_tool_results_pass_independent_checks(self, ctx):
        for name, args in [("get_financial_summary", {}), ("get_cash_position", {}), ("get_receivables_and_payables", {}),
                           ("forecast_cash_flow", {}), ("analyze_expense_changes", {"months": 3}), ("get_upcoming_payments", {}),
                           ("simulate_purchase", {"name": "M", "cost": 1.2e6, "financing": "loan", "loan_rate_pct": 11, "tenure_months": 36})]:
            ok, r = run_tool(ctx, name, args)
            checks = check_tool_result(name, args, r, ctx.ledger, ctx.balances, ctx.obligations)
            assert checks and all(c.ok for c in checks), (name, [c for c in checks if not c.ok])

    def test_tampered_result_is_caught(self, ctx):
        ok, r = run_tool(ctx, "get_financial_summary", {})
        r["revenue"] += 50_000
        checks = check_tool_result("get_financial_summary", {}, r, ctx.ledger, ctx.balances, ctx.obligations)
        assert not all(c.ok for c in checks)
        ok, c = run_tool(ctx, "get_cash_position", {})
        c["cash_balance"] = 2_000_000
        assert not all(x.ok for x in check_tool_result("get_cash_position", {}, c, ctx.ledger, ctx.balances, ctx.obligations))

    def test_answer_figures_must_come_from_tools(self):
        results = [{"revenue": 916164.3, "margin": 0.2245, "date": "2026-09-30", "note": "median 15,000"}]
        ok = verify_answer("Revenue was ₹9,16,164 (22.45%) to 2026-09-30; usual 15,000. That's ₹9.2 lakh.", results, "", set())
        assert ok.ok, ok.answer_issues
        bad = verify_answer("Revenue was ₹9,50,000 and margin 30% by 2026-10-15, see T0999.", results, "", {"T0001"})
        assert bad.unverified_figures == ["₹9,50,000", "30%"]
        assert bad.unknown_dates == ["2026-10-15"] and bad.unknown_ids == ["T0999"]

    def test_ids_quoted_from_tool_text_are_allowed(self):
        r = verify_answer("Largest: Payment for BILL-0047 (U00331).", [{"description": "Payment for BILL-0047", "txn_id": "U00331"}], "", {"U00331"})
        assert r.ok
        assert verify_answer("See BILL-0048.", [{"description": "Payment for BILL-0047"}], "", set()).unknown_ids == ["BILL-0048"]

    def test_user_figures_may_be_repeated(self):
        r = verify_answer("A ₹12 lakh machine at 11% is fine.", [], "Can I buy a ₹12 lakh machine at 11%?", set())
        assert r.ok

    def test_lakh_rounding_tolerance(self):
        assert verify_answer("about ₹14.9 lakh", [1485414.0], "", set()).ok
        assert not verify_answer("about ₹15.9 lakh", [1485414.0], "", set()).ok


# ---------------------------------------------------------------- orchestrator with a scripted model


def text(t):
    return NS(type="text", text=t)


def tool_use(i, name, args):
    return NS(type="tool_use", id=i, name=name, input=args)


class FakeClient:
    """Plays back scripted responses; `script` items are callables(messages) -> (content, stop_reason)."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []
        self.beta = NS(messages=NS(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw)
        content, stop = self.script.pop(0)(kw["messages"])
        return NS(content=content, stop_reason=stop)


def last_tool_result(messages):
    import json

    return json.loads(messages[-1]["content"][0]["content"])


class TestOrchestrator:
    def test_tool_loop_and_verified_answer(self, ctx):
        def answer(msgs):
            cash = last_tool_result(msgs)["cash_balance"]
            return [text(f"**You have {orchestrator_fmt(cash)} in the bank on 2026-09-30.**")], "end_turn"

        client = FakeClient([lambda m: ([text("Checking."), tool_use("a", "get_cash_position", {})], "tool_use"), answer])
        run = run_ai("How much cash do we have?", ctx, client, "test-model", "Demo Co")
        assert [s.tool for s in run.steps] == ["get_cash_position"]
        assert run.verified and not run.warnings and "₹14,85,414" in run.answer
        kw = client.calls[0]
        assert kw["model"] == "test-model" and kw["tools"] and "Demo Co" in kw["system"]
        assert kw["messages"][0] == {"role": "user", "content": "How much cash do we have?"}

    def test_invented_figure_triggers_one_repair(self, ctx):
        client = FakeClient([
            lambda m: ([tool_use("a", "get_cash_position", {})], "tool_use"),
            lambda m: ([text("You have ₹20,00,000.")], "end_turn"),
            lambda m: ([text("You have ₹14,85,414.")], "end_turn"),
        ])
        run = run_ai("cash?", ctx, client, "m", "Demo Co")
        assert run.repaired and run.verified and run.answer == "You have ₹14,85,414."
        assert "Automatic verification" in client.calls[2]["messages"][-2]["content"]

    def test_unrepaired_figure_is_shown_as_a_warning(self, ctx):
        client = FakeClient([lambda m: ([text("Profit is ₹99,99,999.")], "end_turn")] * 2)
        run = run_ai("profit?", ctx, client, "m", "Demo Co")
        assert not run.verified and any("₹99,99,999" in w for w in run.warnings)

    def test_invalid_tool_args_go_back_as_errors(self, ctx):
        seen = {}

        def after(msgs):
            seen.update(msgs[-1]["content"][0])
            return [text("I need a valid date.")], "end_turn"

        client = FakeClient([lambda m: ([tool_use("a", "get_financial_summary", {"start_date": "last year"})], "tool_use"), after])
        run = run_ai("summary", ctx, client, "m", "Demo Co")
        assert seen["is_error"] is True and "YYYY-MM-DD" in seen["content"]
        assert run.steps[0].ok is False

    def test_step_limit(self, ctx):
        loop = lambda m: ([tool_use(f"x{len(m)}", "get_cash_position", {})], "tool_use")  # noqa: E731
        client = FakeClient([loop, loop, lambda m: ([text("Done.")], "end_turn")])
        run = run_ai("cash?", ctx, client, "m", "Demo Co", max_steps=2)
        assert len(run.steps) == 2 and client.calls[-1]["tool_choice"] == {"type": "none"}
        assert any("Stopped after 2" in w for w in run.warnings)

    def test_refusal_and_truncation_are_reported(self, ctx):
        r = run_ai("x", ctx, FakeClient([lambda m: ([], "refusal")]), "m", "Demo Co")
        assert "declined" in r.answer and r.warnings
        r = run_ai("x", ctx, FakeClient([lambda m: ([text("Partial")], "max_tokens")]), "m", "Demo Co")
        assert any("cut off" in w for w in r.warnings)

    def test_api_failure_falls_back_to_rule_based(self, ctx):
        def boom(**kw):
            raise ConnectionError("offline")

        client = NS(beta=NS(messages=NS(create=boom)))
        settings = NS(ai_enabled=True, anthropic_api_key="x", model="m", max_agent_steps=8)
        run = orchestrator.ask("How much cash do we have?", ctx, "Demo Co", settings, client=client)
        assert run.mode == "rule-based" and "AI unavailable" in run.warnings[0] and "₹14,85,414" in run.answer

    def test_no_key_uses_rule_based(self, ctx):
        settings = NS(ai_enabled=False, anthropic_api_key=None, model="m", max_agent_steps=8)
        assert orchestrator.ask("cash?", ctx, "Demo Co", settings).mode == "rule-based"


def orchestrator_fmt(x):
    from finpilot.engine.common import fmt_inr

    return fmt_inr(x)


# ---------------------------------------------------------------- rule-based mode


class TestOffline:
    @pytest.mark.parametrize(
        "q,tool",
        [
            ("How profitable were we in the last 6 months?", "get_financial_summary"),
            ("Why did expenses go up last month?", "analyze_expense_changes"),
            ("Any duplicate payments?", "find_unusual_transactions"),
            ("How much cash do we have?", "get_cash_position"),
            ("Who owes us money?", "get_receivables_and_payables"),
            ("Forecast our cash for the next 90 days", "forecast_cash_flow"),
            ("Can we afford a ₹12 lakh packing machine on a loan at 11% for 3 years? It would save ₹45,000 a month.", "simulate_purchase"),
            ("Show T0012 and INV-0050", "get_supporting_records"),
        ],
    )
    def test_answers_use_tools_and_verify(self, ctx, q, tool):
        run = run_offline(q, ctx)
        assert tool in [s.tool for s in run.steps]
        assert run.verified, run.warnings

    def test_purchase_parsing(self, ctx):
        run = run_offline("Can we afford a ₹12 lakh packing machine on a loan at 11% for 3 years? It would save ₹45,000 a month.", ctx)
        args = next(s.args for s in run.steps if s.tool == "simulate_purchase")
        assert args["cost"] == 1_200_000 and args["loan_rate_pct"] == 11 and args["tenure_months"] == 36
        assert args["monthly_benefit"] == 45_000 and args["financing"] == "loan"

    def test_loan_without_terms_asks(self, ctx):
        run = run_offline("Can we buy a ₹8 lakh van on a loan?", ctx)
        assert "more detail" in run.answer and run.verified

    def test_no_balance_says_unknown(self, demo):
        c = ToolContext(demo["ledger"], demo["obligations"], None, AS_OF, None)
        for q in ("How much cash do we have?", "Forecast cash for 60 days", "Can we afford a ₹3 lakh oven?"):
            assert "unknown" in run_offline(q, c).answer.lower() or "can't" in run_offline(q, c).answer.lower()

    def test_help_for_unrecognised_question(self, ctx):
        run = run_offline("hello", ctx)
        assert not run.steps and "Namaste" in run.answer
        run = run_offline("blah blah", ctx)
        assert not run.steps and "I can help with" in run.answer


class TestHindi:
    def test_hindi_amounts_and_tenure(self, ctx):
        q = "क्या मैं ₹12 लाख की मशीन 11% पर 3 साल के लोन पर ले सकता हूँ? हर महीने ₹45,000 बचेंगे"
        run = run_offline(q, ctx, lang="hi")
        args = next(s.args for s in run.steps if s.tool == "simulate_purchase")
        assert args["cost"] == 1_200_000 and args["tenure_months"] == 36 and args["loan_rate_pct"] == 11
        assert args["monthly_benefit"] == 45_000
        assert run.verified and "EMI" in run.answer and "₹31,429" in run.answer

    @pytest.mark.parametrize("q,tool", [
        ("बैंक में कितना पैसा है?", "get_cash_position"),
        ("किस पर उधारी बाकी है?", "get_receivables_and_payables"),
        ("pichle mahine kharcha kyun badha?", "analyze_expense_changes"),
        ("अगले 60 दिन का अनुमान", "forecast_cash_flow"),
        ("कोई दोहरा भुगतान?", "find_unusual_transactions"),
    ])
    def test_hindi_questions_route_and_verify(self, ctx, q, tool):
        run = run_offline(q, ctx, lang="hi")
        assert tool in [s.tool for s in run.steps] and run.verified, run.warnings
        assert any("ऀ" <= ch <= "ॿ" for ch in run.answer)  # answered in Devanagari

    def test_verifier_reads_lakh_in_hindi(self):
        assert verify_answer("लगभग ₹14.9 लाख", [1485414.0], "", set()).ok
        assert not verify_answer("लगभग ₹19 लाख", [1485414.0], "", set()).ok
