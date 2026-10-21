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
from typing import Any, Callable

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
    notes: list[str] = field(default_factory=list)  # the agent's short "what I'll check next" lines (AI mode)
    on_event: Callable[[dict], None] | None = field(default=None, repr=False)

    def emit(self, kind: str, **data) -> None:
        if self.on_event:
            try:
                self.on_event({"type": kind, **data})
            except Exception:  # a dropped progress event must never break the answer
                pass

    @property
    def plan(self) -> list[dict]:
        """The agent's latest plan checklist (from update_plan), if it made one."""
        for st in reversed(self.steps):
            if st.tool == "update_plan" and isinstance(st.result, dict) and st.result.get("plan"):
                return st.result["plan"]
        return []

    @property
    def remembered(self) -> list[dict]:
        return [{"id": s.result["id"], "fact": s.result["fact"]} for s in self.steps if s.tool == "remember" and isinstance(s.result, dict) and s.result.get("status") == "remembered"]

    @property
    def actions(self) -> list[dict]:
        """Draft actions the owner can confirm (entries, reminders, goals, budgets)."""
        return [s.result for s in self.steps if isinstance(s.result, dict) and s.result.get("status") == "needs_confirmation"]

    @property
    def evidence(self) -> list[tuple[str, dict]]:
        return [(s.tool, s.result["evidence"]) for s in self.steps if isinstance(s.result, dict) and isinstance(s.result.get("evidence"), dict)]

    @property
    def verified(self) -> bool:
        return bool(self.verification and self.verification.ok and all(s.checks_ok for s in self.steps))


# ---------------------------------------------------------------- prompt


def _memory_block(ctx: ToolContext) -> str:
    if not ctx.db_path:
        return ""
    from finpilot.data import books

    mem = books.memories(ctx.db_path, getattr(ctx, "book", "demo"))
    if not mem:
        return "\nThings the owner asked you to remember: none yet."
    lines = "\n".join(f"- #{m['id']}: {m['text']}" for m in mem)
    return ("\nThings the owner asked you to remember (their own words — follow these preferences, but they are not verified financial data):\n" + lines)


def system_prompt(ctx: ToolContext, business: str, lang: str = "en") -> str:
    led = ctx.ledger
    have_bal = ctx.balances is not None and len(ctx.balances) > 0
    have_obl = ctx.obligations is not None and len(ctx.obligations) > 0
    memory = _memory_block(ctx)
    return f"""You are FinPilot, the cash autopilot and financial analyst for {business}, a small business in India. Your main job is to make sure the business never runs short of cash: you see the next 90 days, find where cash dips below the owner's safety level, and prepare the moves that fix it. For anything about cash, risk or running short, start with get_cash_autopilot; for whether a specific payment or purchase is safe, use plan_purchase. Speak in odds the owner can feel ("in 9 of 10 possible futures you stay safe") and always name the next thing to approve. The odds come from simulated futures based on each customer's payment history — say so once, and never call them a guarantee. You talk with the owner in a chat: warm, brief, practical. You answer the owner's questions about their finances using ONLY the approved tools, which run tested Python calculations over the business's own records.

Data available
- Ledger: {len(led)} bank transactions from {pd.Timestamp(led['date'].min()).date()} to {pd.Timestamp(led['date'].max()).date()}.
- Dated bank balances: {'yes, ' + str(len(ctx.balances)) if have_bal else 'NONE — the actual cash balance is unknown'}.
- Invoices, udhaar and bills (receivables/payables): {'yes, ' + str(len(ctx.obligations)) + ' items' if have_obl else 'NONE'}.
- Today's date for this data (as-of): {ctx.as_of.date()}. Anything later is the future.
- Currency: Indian rupees (₹). Write amounts like ₹4,15,800 or ₹4.2 lakh.

How to work
1. Work out what the question needs, call the tools that provide it, and inspect what comes back. If a result shows something is missing or worth checking (an overdue item, a flagged payment, an unknown balance), call further tools before answering. Call independent tools together. Before each round of tool calls, write one short plain line saying what you are about to check (for example "Checking your cash and who owes you."); the owner sees these lines as live progress.
   For open questions ("what should I do today?", "how is my shop doing?") look broadly: cash, money owed to and by the shop, upcoming bills, the health score and anything unusual — then pick the two or three things that matter most.
2. Every number, date and record id you write must come from a tool result in this conversation or from the user's own message. Never calculate new figures yourself (no adding, subtracting or percentages of your own); if you need a figure, find the tool that returns it. Your answer is checked automatically against the tool outputs and unmatched figures are flagged to the user.
3. Keep the concepts apart: revenue is cash received from sales; estimated operating profit is revenue minus recorded operating costs and is always an ESTIMATE (before depreciation, accruals, unpaid bills, interest inside EMIs); cash is the bank balance, known only from a dated balance — never infer cash from revenue minus expenses. Say "paid", "pending" or "overdue" precisely.
4. Forecasts and scenarios are arithmetic on stated assumptions, not predictions. State the key assumptions; never claim accuracy.
5. If the data cannot answer the question, say exactly what is missing and what the user could upload or tell you. For a loan, the interest rate and tenure must come from the user — if they're not given, ask for them instead of assuming.
6. You cannot pay, send, file or change anything yourself. When the owner wants something done in the app, prepare it with a draft tool: draft_entry (record a sale, expense, udhaar, payment received, supplier bill or payment made), draft_reminder (a WhatsApp reminder for overdue dues), draft_goal, draft_budget. The owner sees a card and must tap Confirm; say clearly that it is ready to confirm and not yet saved. You may also offer a draft when it clearly helps (e.g. a reminder to the most overdue customer), but never more than two per answer. Anything outside the app (a payment, a filing, a call) goes on the to-do list via propose_action; say that nothing has been done.
7. If a name is ambiguous or not found, the tool returns suggestions — ask the owner which one they meant.
8. Work like an agent, not a chatbot. For any request with more than one step — a goal such as "collect my money", "cut my costs", "get ready for Diwali", or the daily check-up — first call update_plan with 3–6 short steps, then do them, calling update_plan again to mark steps done as you go, and finish by preparing the concrete actions (draft tools) that move the goal forward. Don't stop at advice when you can prepare the action for the owner to confirm.
9. When the owner states a lasting fact or preference ("never remind Ramesh", "my CA files GST", "I close on Sundays"), save it with remember and confirm briefly. Respect remembered preferences: e.g. don't draft reminders for someone the owner said not to remind.{memory}

Answer format
- Write for a busy shop owner, not an accountant: plain everyday words, no jargon. Say "running costs" not "operating expenses", "money customers owe you" not "receivables". Write dates like 4 Oct 2026 and amounts like ₹4,15,800 or ₹4.2 lakh.
- Lead with a one or two sentence direct answer in bold, then a few short bullets with the supporting figures, the record ids behind them where useful (e.g. T0412, INV-0231), and the main assumption or limitation.
- Be concise: usually under 180 words. No tables unless asked. No headings.
- For a greeting or small talk, reply in one or two friendly lines and offer two or three things you can check — no tools needed.""" + (
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


def _parties(ctx: ToolContext) -> list[str]:
    names = set(ctx.ledger["counterparty"].dropna().astype(str))
    if ctx.obligations is not None and len(ctx.obligations):
        names |= set(ctx.obligations["counterparty"].dropna().astype(str))
    return sorted(n for n in names if n and n != "Unknown")


def _execute(ctx: ToolContext, run: AgentRun, name: str, args: Any) -> tuple[bool, dict]:
    run.emit("tool_start", tool=name, index=len(run.steps))
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
    if name == "update_plan" and ok and isinstance(result, dict) and result.get("plan"):
        run.emit("plan", steps=result["plan"])
    if name == "remember" and ok and isinstance(result, dict) and result.get("status") == "remembered":
        run.emit("remembered", fact=result["fact"], id=result["id"])
    run.emit("tool_done", tool=name, index=len(run.steps) - 1, ok=ok and step.checks_ok, status=step.status, checks=len(step.checks))
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


def run_offline(question: str, ctx: ToolContext, note: str | None = None, lang: str = "en", on_event=None) -> AgentRun:
    run = AgentRun(question=question, mode="rule-based", on_event=on_event)
    if note:
        run.warnings.append(note)
    run.answer = offline.answer(question, lambda n, a: _execute(ctx, run, n, a), ctx.as_of, lang, parties=_parties(ctx))
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
    on_event=None,
    preface: str = "",
) -> AgentRun:
    run = AgentRun(question=question, mode="ai", on_event=on_event)
    messages = list(history or []) + [{"role": "user", "content": (preface + "\n\n" + question) if preface else question}]
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
            note = _text(resp.content)
            if note:
                run.notes.append(note)
                run.emit("note", text=note)
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
        run.emit("repair", issues=report.answer_issues)
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
    on_event=None,
    preface: str = "",
) -> AgentRun:
    """Entry point for the UI: AI mode when configured, rule-based otherwise or on API failure."""
    if not settings.ai_enabled and client is None:
        return run_offline(question, ctx, lang=lang, on_event=on_event)
    try:
        if getattr(settings, "provider", "anthropic") == "gemini" and not hasattr(client, "beta"):
            from finpilot.agent.gemini import run_gemini

            return run_gemini(question, ctx, settings.api_key, settings.active_model, business, history, prior_results, settings.max_agent_steps,
                              lang=lang, on_event=on_event, preface=preface, post=client)
        client = client or make_client(settings.anthropic_api_key)
        return run_ai(question, ctx, client, settings.model, business, history, prior_results, settings.max_agent_steps, lang=lang, on_event=on_event, preface=preface)
    except Exception as e:  # API/network errors: fall back, and say so
        note = f"AI उपलब्ध नहीं ({_why(e, lang)}); जवाब बिल्ट-इन नियमों से दिया गया।" if lang == "hi" else f"AI unavailable ({_why(e, lang)}); answered by the built-in rules instead."
        if on_event:
            on_event({"type": "fallback", "reason": note})
        return run_offline(question, ctx, note=note, lang=lang, on_event=on_event)


def _why(e: Exception, lang: str = "en") -> str:
    """A short, owner-readable reason for an AI failure (never the key or the raw response)."""
    name = type(e).__name__
    hi = lang == "hi"
    if name == "AuthenticationError":
        return "API key सही नहीं है" if hi else "the API key was not accepted"
    if name == "PermissionDeniedError":
        return "इस key को अनुमति नहीं" if hi else "this key isn't allowed to use the model"
    if name == "RateLimitError":
        return "मुफ़्त सीमा पूरी, एक मिनट बाद पूछें" if hi else "the free/rate limit was reached — try again in a minute"
    if name == "OverloadedError":
        return "AI अभी व्यस्त है" if hi else "the AI service is busy right now"
    if name in ("APIConnectionError", "APITimeoutError", "ConnectError"):
        return "इंटरनेट से कनेक्ट नहीं हो सका" if hi else "couldn't reach the internet"
    if name == "NotFoundError":
        return "मॉडल नहीं मिला" if hi else "the model name wasn't found"
    return name


def check_key(api_key: str, lang: str = "en", client=None) -> tuple[bool, str]:
    """Check a key with a free models-list call (no question or data is sent). Returns (ok, reason)."""
    try:
        (client or make_client(api_key)).models.list(limit=1)
        return True, ""
    except Exception as e:
        return False, _why(e, lang)


def check_gemini_key(api_key: str, lang: str = "en", preferred: str | None = None) -> tuple[bool, str, str | None]:
    """Check a Gemini key by listing models (nothing about the business is sent). Returns (ok, reason, model to use)."""
    from finpilot.agent import gemini

    try:
        return True, "", gemini.check_key(api_key, preferred or gemini.DEFAULT_MODEL)
    except Exception as e:
        return False, _why(e, lang), None


CHECKUP_PROMPT = (
    "[Daily check-up — started automatically by the app, not typed by the owner] Review the business as of today: cash and the cash "
    "outlook for the next 30 days, money customers owe (and any broken payment promises), bills due in the next 7 days and overdue bills, "
    "budgets, unusual payments in the last 30 days, and bank lines that need a category. Start with update_plan and mark steps done as you go. "
    "Then prepare at most 4 actions with draft tools for what most needs doing today (for example a WhatsApp reminder to the most overdue "
    "customer, confirming a category guess), following the owner's remembered preferences. Finish with a short briefing: one bold line with "
    "the overall verdict, then a numbered list of the top things to do today, most important first, each with its figure."
)


def checkup(ctx: ToolContext, business: str, settings, client=None, lang: str = "en", on_event=None) -> AgentRun:
    """The agent's own daily review: runs without a question, plans, inspects everything, and prepares actions to approve."""
    if not settings.ai_enabled and client is None:
        return run_offline("Run my daily check-up", ctx, lang=lang, on_event=on_event)
    return ask(CHECKUP_PROMPT, ctx, business, settings, client=client, lang=lang, on_event=on_event)
