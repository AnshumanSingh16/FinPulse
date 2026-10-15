"""
The orchestrating agent.

One model drives a manual tool-use loop over the approved tools in finpilot.agent.tools:
it reads the question, chooses tools, gets validated results back, may call more, then answers.
This module owns everything around that loop:

- arguments are validated by Python before any tool runs; invalid ones come back as errors;
- every tool result is independently re-checked (verify.check_tool_result);
- the final answer is checked figure by figure against the tool outputs (verify.verify_answer).
  If anything doesn't match, the model gets one repair turn; anything still unmatched is shown
  to the user as a warning rather than passed off as verified;
- a hard step limit stops runaway loops;
- with no API key (or if the API call fails) the same tools run through the rule-based router
  in finpilot.agent.offline, and the answer is labelled as such.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from finpilot.agent import offline
from finpilot.agent.tools import ToolContext, anthropic_tool_specs, run_tool
from finpilot.agent.verify import Check, VerificationReport, check_tool_result, verify_answer

MAX_TOKENS = 16000
BETAS = ["server-side-fallback-2026-07-01"]


@dataclass
class Step:
    tool: str
    args: dict
    ok: bool
    result: dict
    checks: list[Check] = field(default_factory=list)

    @property
    def status(self) -> str:
        return self.result.get("status", "error") if isinstance(self.result, dict) else "error"

    @property
    def checks_ok(self) -> bool:
        return all(c.ok for c in self.checks)


@dataclass
class AgentRun:
    question: str
    answer: str = ""
    mode: str = "ai"  # "ai" or "rule-based"
    steps: list[Step] = field(default_factory=list)
    verification: VerificationReport | None = None
    warnings: list[str] = field(default_factory=list)
    repaired: bool = False
    messages: list = field(default_factory=list)  # full API history after this run (AI mode)

    @property
    def evidence(self) -> list[tuple[str, dict]]:
        return [(s.tool, s.result["evidence"]) for s in self.steps if isinstance(s.result, dict) and isinstance(s.result.get("evidence"), dict)]

    @property
    def verified(self) -> bool:
        return bool(self.verification and self.verification.ok and all(s.checks_ok for s in self.steps))


# ---------------------------------------------------------------- prompt


def system_prompt(ctx: ToolContext, business: str, lang: str = "en") -> str:
    led = ctx.ledger
    have_bal = ctx.balances is not None and len(ctx.balances) > 0
    have_obl = ctx.obligations is not None and len(ctx.obligations) > 0
    return f"""You are FinPilot, a financial analyst for {business}, a small business in India. You answer the owner's questions about their finances using ONLY the approved tools, which run tested Python calculations over the business's own records.

Data available
- Ledger: {len(led)} bank transactions from {pd.Timestamp(led['date'].min()).date()} to {pd.Timestamp(led['date'].max()).date()}.
- Dated bank balances: {'yes, ' + str(len(ctx.balances)) if have_bal else 'NONE — the actual cash balance is unknown'}.
- Invoices and bills (receivables/payables): {'yes, ' + str(len(ctx.obligations)) + ' items' if have_obl else 'NONE'}.
- Today's date for this data (as-of): {ctx.as_of.date()}. Anything later is the future.
- Currency: Indian rupees (₹). Write amounts like ₹4,15,800 or ₹4.2 lakh.

How to work
1. Work out what the question needs, call the tools that provide it, and inspect what comes back. If a result shows something is missing or worth checking (an overdue item, a flagged payment, an unknown balance), call further tools before answering. Call independent tools together.
2. Every number, date and record id you write must come from a tool result in this conversation or from the user's own message. Never calculate new figures yourself (no adding, subtracting or percentages of your own); if you need a figure, find the tool that returns it. Your answer is checked automatically against the tool outputs and unmatched figures are flagged to the user.
3. Keep the concepts apart: revenue is cash received from sales; estimated operating profit is revenue minus recorded operating costs and is always an ESTIMATE (before depreciation, accruals, unpaid bills, interest inside EMIs); cash is the bank balance, known only from a dated balance — never infer cash from revenue minus expenses. Say "paid", "pending" or "overdue" precisely.
4. Forecasts and scenarios are arithmetic on stated assumptions, not predictions. State the key assumptions; never claim accuracy.
5. If the data cannot answer the question, say exactly what is missing and what the user could upload or tell you. For a loan, the interest rate and tenure must come from the user — if they're not given, ask for them instead of assuming.
6. You cannot pay, send, file or change anything. If the user asks for an action (a reminder, a payment, a filing), use propose_action to queue it for human approval and say that nothing has been done.

Answer format
- Write for a busy shop owner, not an accountant: plain everyday words, no jargon. Say "running costs" not "operating expenses", "money customers owe you" not "receivables". Write dates like 4 Oct 2026 and amounts like ₹4,15,800 or ₹4.2 lakh.
- Lead with a one or two sentence direct answer in bold, then a few short bullets with the supporting figures, the record ids behind them where useful (e.g. T0412, INV-0231), and the main assumption or limitation.
- Be concise: usually under 180 words. No tables unless asked. No headings.""" + (
        "\n- Reply in simple Hindi (Devanagari script), as a shopkeeper speaks it; keep amounts as ₹ with Western digits (₹4,15,800), and record ids as they are."
        if lang == "hi" else "")


# ---------------------------------------------------------------- helpers


def _block(b: Any, key: str, default=None):
    return b.get(key, default) if isinstance(b, dict) else getattr(b, key, default)


def _text(content) -> str:
    return "\n".join(_block(b, "text", "") for b in content if _block(b, "type") == "text").strip()


def _known_ids(ctx: ToolContext) -> set[str]:
    ids = set(ctx.ledger["txn_id"].astype(str))
    if ctx.obligations is not None and len(ctx.obligations):
        ids |= set(ctx.obligations["item_id"].astype(str))
    return ids


def _execute(ctx: ToolContext, run: AgentRun, name: str, args: Any) -> tuple[bool, dict]:
    ok, result = run_tool(ctx, name, args)
    step = Step(name, args if isinstance(args, dict) else {"_raw": args}, ok, result)
    if ok:
        try:
            step.checks = check_tool_result(name, args, result, ctx.ledger, ctx.balances, ctx.obligations)
        except Exception as e:  # a checker crash is itself a failed check, never a silent pass
            step.checks = [Check("independent re-check ran", False, f"{type(e).__name__}: {e}")]
        bad = [c for c in step.checks if not c.ok]
        if bad:
            run.warnings.append(f"{name}: independent check failed — " + "; ".join(f"{c.name} ({c.detail})" for c in bad))
            result = {**result, "verification_warning": "This result failed an independent arithmetic check; tell the user it could not be verified."}
    run.steps.append(step)
    return ok, result


def _verify(run: AgentRun, ctx: ToolContext, answer: str, prior_results: list) -> VerificationReport:
    return verify_answer(
        answer,
        [s.result for s in run.steps] + list(prior_results),
        run.question,
        _known_ids(ctx),
        extra_dates={str(ctx.as_of.date())},
    )


# ---------------------------------------------------------------- modes


def run_offline(question: str, ctx: ToolContext, note: str | None = None, lang: str = "en") -> AgentRun:
    run = AgentRun(question=question, mode="rule-based")
    if note:
        run.warnings.append(note)
    run.answer = offline.answer(question, lambda n, a: _execute(ctx, run, n, a), ctx.as_of, lang)
    if not run.steps:  # help text: no financial claims to verify
        return run
    run.verification = _verify(run, ctx, run.answer, [])
    if not run.verification.ok:
        run.warnings.extend(run.verification.answer_issues)
    return run


def run_ai(
    question: str,
    ctx: ToolContext,
    client,
    model: str,
    business: str,
    history: list | None = None,
    prior_results: list | None = None,
    max_steps: int = 8,
    effort: str = "medium",
    lang: str = "en",
) -> AgentRun:
    run = AgentRun(question=question, mode="ai")
    messages = list(history or []) + [{"role": "user", "content": question}]
    prior_results = prior_results or []
    tools = anthropic_tool_specs()
    system = system_prompt(ctx, business, lang)
    tool_rounds = 0
    repairs_left = 1
    force_answer = False

    while True:
        kwargs = dict(
            model=model,
            max_tokens=MAX_TOKENS,
            betas=BETAS,
            fallbacks="default",
            thinking={"type": "adaptive"},
            output_config={"effort": effort},
            system=system,
            tools=tools,
            messages=messages,
        )
        if force_answer:
            kwargs["tool_choice"] = {"type": "none"}
        resp = client.beta.messages.create(**kwargs)
        messages.append({"role": "assistant", "content": resp.content})
        stop = resp.stop_reason

        if stop == "pause_turn":
            continue

        if stop == "tool_use":
            tool_rounds += 1
            results = []
            for b in resp.content:
                if _block(b, "type") != "tool_use":
                    continue
                ok, result = _execute(ctx, run, _block(b, "name"), _block(b, "input"))
                results.append({"type": "tool_result", "tool_use_id": _block(b, "id"), "content": json.dumps(result, default=str), "is_error": not ok})
            if tool_rounds >= max_steps:
                force_answer = True
                results.append({"type": "text", "text": f"Step limit of {max_steps} tool rounds reached. Answer now from the results you have, and say what you could not check."})
                run.warnings.append(f"Stopped after {max_steps} rounds of tool calls.")
            messages.append({"role": "user", "content": results})
            continue

        answer = _text(resp.content)
        if stop == "refusal":
            run.answer = answer or "FinPilot's AI declined to answer this question. Try rephrasing it as a question about the business's records."
            run.warnings.append("The model declined this request.")
            break
        if stop == "max_tokens":
            run.answer = answer
            run.warnings.append("The answer was cut off at the length limit.")
            break

        report = _verify(run, ctx, answer, prior_results)
        if report.ok or repairs_left == 0:
            run.answer, run.verification = answer, report
            if not report.ok:
                run.warnings.extend(report.answer_issues)
            break
        repairs_left -= 1
        run.repaired = True
        force_answer = False
        messages.append(
            {
                "role": "user",
                "content": "[Automatic verification — not from the user] Your answer contains "
                + "; ".join(report.answer_issues)
                + ". Every figure, date and record id must appear in a tool result. Call tools if you need the figure, or remove it. Reply with the full corrected answer only.",
            }
        )

    if run.verification is None and run.answer:
        run.verification = _verify(run, ctx, run.answer, prior_results)
        if not run.verification.ok:
            run.warnings.extend(run.verification.answer_issues)
    run.messages = messages
    return run


def make_client(api_key: str):
    import anthropic

    return anthropic.Anthropic(api_key=api_key)


def ask(
    question: str,
    ctx: ToolContext,
    business: str,
    settings,
    client=None,
    history: list | None = None,
    prior_results: list | None = None,
    lang: str = "en",
) -> AgentRun:
    """Entry point for the UI: AI mode when configured, rule-based otherwise or on API failure."""
    if not settings.ai_enabled and client is None:
        return run_offline(question, ctx, lang=lang)
    try:
        client = client or make_client(settings.anthropic_api_key)
        return run_ai(question, ctx, client, settings.model, business, history, prior_results, settings.max_agent_steps, lang=lang)
    except Exception as e:  # API/network errors: fall back, and say so
        note = f"AI उपलब्ध नहीं ({type(e).__name__}); जवाब बिल्ट-इन नियमों से दिया गया।" if lang == "hi" else f"AI unavailable ({type(e).__name__}); answered by the rule-based engine instead."
        return run_offline(question, ctx, note=note, lang=lang)
