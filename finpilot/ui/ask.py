"""Ask FinPilot: conversational analysis with the tool activity, verification and evidence shown."""

from __future__ import annotations

import html
import json

import pandas as pd
import streamlit as st

from finpilot.agent import orchestrator
from finpilot.agent.tools import ToolContext
from finpilot.config import settings
from finpilot.ui import components as c
from finpilot.ui import state

SUGGESTIONS = [
    "How is the business doing over the last 6 months?",
    "Why did expenses go up last month?",
    "Any duplicate or unusual payments?",
    "Who owes us money, and what bills are due?",
    "Forecast our cash for the next 90 days.",
    "Can we afford a ₹12 lakh packing machine on a loan at 11% for 3 years? It would save ₹45,000 a month.",
]

TOOL_LABEL = {
    "get_financial_summary": "Financial summary",
    "analyze_expense_changes": "Expense comparison",
    "find_unusual_transactions": "Unusual-transaction scan",
    "get_cash_position": "Cash position",
    "get_receivables_and_payables": "Receivables & payables",
    "get_upcoming_payments": "Upcoming payments",
    "forecast_cash_flow": "Cash-flow forecast",
    "simulate_purchase": "Purchase simulation",
    "get_supporting_records": "Supporting records",
    "propose_action": "Approval queue",
}


def _chat_key(ds: state.Dataset) -> str:
    return f"chat::{ds.source}::{ds.name}::{ds.as_of.date()}"


def _badge(run: orchestrator.AgentRun) -> str:
    mode = "AI agent" if run.mode == "ai" else "Rule-based (no AI)"
    if not run.steps:
        status = '<span class="fp-tag">no figures</span>'
    elif run.verified:
        status = '<span class="fp-tag verified">✓ figures verified</span>'
    else:
        status = '<span class="fp-tag est">⚠ check warnings</span>'
    rep = ' <span class="fp-tag">repaired once</span>' if run.repaired else ""
    return f'<div style="margin:.15rem 0 .4rem">{status}{rep} <span class="fp-tag">{html.escape(mode)}</span></div>'


def _records_for(ids: list[str], ds: state.Dataset):
    if not ids:
        return None, "txn_id"
    if ds.ledger["txn_id"].isin(ids).any():
        return ds.ledger, "txn_id"
    if ds.obligations is not None and ds.obligations["item_id"].isin(ids).any():
        return ds.obligations, "item_id"
    return None, "txn_id"


def _activity(run: orchestrator.AgentRun, ds: state.Dataset, key: str) -> None:
    if not run.steps:
        return
    n_checks = sum(len(s.checks) for s in run.steps)
    n_ok = sum(c_.ok for s in run.steps for c_ in s.checks)
    with st.expander(f"Tool activity · {len(run.steps)} call(s) · {n_ok}/{n_checks} independent checks passed", expanded=False):
        for i, s in enumerate(run.steps, 1):
            args = ", ".join(f"{k}={json.dumps(v, ensure_ascii=False)}" for k, v in s.args.items()) or "no arguments"
            mark = "✓" if s.ok and s.checks_ok else ("✗" if not s.ok else "⚠")
            st.markdown(
                f'<div class="fp-tool">{i}. <code>{s.tool}</code> — {html.escape(TOOL_LABEL.get(s.tool, s.tool))} '
                f"· {html.escape(args)} · <b>{mark} {html.escape(s.status)}</b></div>",
                unsafe_allow_html=True,
            )
            if not s.ok:
                st.caption(s.result.get("message", ""))
            for chk in s.checks:
                st.caption(f"{'✓' if chk.ok else '✗'} {chk.name} — {chk.detail}")
        if run.verification:
            v = run.verification
            st.caption(
                "Answer check: every ₹ amount, percentage, date and record id in the answer was matched against the tool outputs above"
                + (" — all matched." if v.ok else ". Unmatched items are listed in the warning.")
            )
    seen = set()
    for j, (tool, ev) in enumerate(run.evidence):
        if tool in seen:
            continue
        seen.add(tool)
        recs, col = _records_for(ev.get("record_ids") or [], ds)
        c.evidence_panel(ev, recs, title=f"Evidence · {TOOL_LABEL.get(tool, tool)}", id_col=col, key=f"{key}_{j}")


def _render_turn(turn: dict, ds: state.Dataset, idx: int) -> None:
    with st.chat_message("user"):
        st.markdown(turn["question"])
    run: orchestrator.AgentRun = turn["run"]
    with st.chat_message("assistant", avatar=":material/insights:"):
        st.markdown(_badge(run), unsafe_allow_html=True)
        st.markdown(run.answer or "_No answer._")
        for w in run.warnings:
            st.warning(w, icon=":material/warning:")
        _activity(run, ds, key=f"t{idx}")


def render() -> None:
    ds = state.current()
    cfg = settings()
    c.header("Ask FinPilot", "Ask about your finances", f"{ds.name} · data to {ds.as_of.date():%d %b %Y}")

    if cfg.ai_enabled:
        st.info(
            f"**AI mode ({cfg.model}).** All figures are calculated locally in Python by approved tools. To write the answer, your question "
            "and the tools' outputs (totals plus the specific records they return) are sent to Anthropic's API. Your uploaded files themselves are not sent. "
            "If the primary model is unavailable or declines, a server-side fallback model may answer.",
            icon=":material/shield:",
        )
    else:
        st.info(
            "**Rule-based mode — no AI key configured.** Questions are matched to the same approved tools and answered from templates; nothing leaves this computer. "
            "Set `ANTHROPIC_API_KEY` to enable the AI agent (see README).",
            icon=":material/offline_bolt:",
        )

    key = _chat_key(ds)
    chat: list[dict] = st.session_state.setdefault(key, [])
    agent_state = st.session_state.setdefault(key + "::agent", {"messages": [], "results": []})

    for i, turn in enumerate(chat):
        _render_turn(turn, ds, i)

    picked = None
    if not chat:
        st.markdown("##### Try one of these")
        picked = st.pills("Suggested questions", SUGGESTIONS, key=f"sugg_{len(chat)}", label_visibility="collapsed")
    question = st.chat_input("Ask about revenue, expenses, cash, bills, forecasts or a purchase…") or picked

    if chat:
        if st.button("Clear conversation", icon=":material/delete_sweep:", type="tertiary"):
            st.session_state[key] = []
            st.session_state[key + "::agent"] = {"messages": [], "results": []}
            st.rerun()

    if question:
        ctx = ToolContext(ds.ledger, ds.obligations, ds.balances, ds.as_of, cfg.db_path)
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant", avatar=":material/insights:"):
            with st.spinner("Analysing with approved tools…"):
                run = orchestrator.ask(
                    question, ctx, ds.name, cfg,
                    history=agent_state["messages"], prior_results=agent_state["results"],
                )
        if run.mode == "ai" and run.messages:
            agent_state["messages"] = run.messages
            agent_state["results"] += [s.result for s in run.steps]
        chat.append({"question": question, "run": run})
        st.rerun()

    st.caption("FinPilot gives decision support from your records, not financial advice. It cannot make payments, send messages or file returns — suggested actions go to the approval queue on the Data page.")
