"""
HTTP API for the FinPilot web app, plus the built front end. Runs locally; nothing is sent anywhere
except, in AI mode, the question and tool outputs to the chosen AI provider (Anthropic or Google Gemini; see README).
"""

from __future__ import annotations

import copy
import json
import mimetypes
import os
import queue
import re
import threading
import time
import uuid
from contextvars import ContextVar
from pathlib import Path

import pandas as pd
from fastapi import Body, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from finpilot.agent import orchestrator
from finpilot.agent.tools import ToolContext
from finpilot import config
from finpilot.config import settings
from finpilot.data import books, khata, loader, store
from finpilot.data.parse_entry import parse as parse_entry
from finpilot.engine import autopilot as ap
from finpilot.engine.cash import cash_position, obligations_status
from finpilot.engine.categorize import categorize_ledger

from . import crew, dataset, i18n, khata_views, monitor, smart_views, views

STATIC = Path(__file__).resolve().parents[1] / "web"

# Windows reads file types from the registry, which some installs map wrongly (e.g. .js as text/plain).
for _ext, _type in ((".js", "text/javascript"), (".mjs", "text/javascript"), (".css", "text/css"), (".html", "text/html"), (".txt", "text/plain"),
                    (".json", "application/json"), (".svg", "image/svg+xml"), (".woff2", "font/woff2"), (".woff", "font/woff"), (".ico", "image/x-icon")):
    mimetypes.add_type(_type, _ext)
MAX_UPLOAD = 25 * 1024 * 1024

KINDS = {"bank": "ledger", "invoices": "obligations", "balances": "balances"}
REQUIRED = {"ledger": [("date",), ("amount", "debit", "credit")], "obligations": [("amount",), ("due_date",)], "balances": [("as_of",), ("balance",)]}

STEP_LABEL = {
    "get_financial_summary": "Worked out sales and costs (cash basis)",
    "investigate_sales_change": "Investigated why sales changed",
    "get_cash_autopilot": "Looked 90 days ahead and checked the plan",
    "plan_purchase": "Tested the payment against your cash",
    "test_move": "Tested an idea on your forecast",
    "get_track_record": "Checked how accurate past forecasts were",
    "analyze_expense_changes": "Compared your costs month to month",
    "find_unusual_transactions": "Looked for unusual or double payments",
    "get_cash_position": "Checked your bank balance",
    "get_receivables_and_payables": "Checked who owes you and what you owe",
    "get_upcoming_payments": "Looked at bills coming up",
    "forecast_cash_flow": "Projected your cash ahead",
    "simulate_purchase": "Tested the purchase against your cash",
    "get_supporting_records": "Pulled up the exact records",
    "propose_action": "Added a to-do for you to approve",
    "get_customers_and_suppliers": "Went through your khata",
    "get_person_details": "Opened their khata page",
    "get_health_score": "Worked out your health score",
    "get_weekly_story": "Looked at the last 7 days",
    "get_budgets_and_goals": "Checked your budgets and goals",
    "get_tax_calendar_and_gst": "Checked GST and tax dates",
    "run_what_if": "Ran the numbers on your averages",
    "draft_entry": "Prepared the entry for you to confirm",
    "draft_reminder": "Drafted a WhatsApp reminder",
    "draft_goal": "Prepared a savings goal",
    "draft_budget": "Prepared a budget",
    "update_plan": "Updated the plan",
    "remember": "Saved to memory",
    "forget": "Removed from memory",
    "recall_memory": "Checked what you asked me to remember",
    "get_review_queue": "Checked lines needing a category",
    "draft_promise": "Prepared a promise note",
    "draft_recategorise": "Prepared a category fix",
}
STEP_LABEL_HI = {
    "get_financial_summary": "बिक्री और खर्च निकाला (कैश के हिसाब से)",
    "investigate_sales_change": "बिक्री बदलने की वजह की जाँच की",
    "get_cash_autopilot": "90 दिन आगे देखा और योजना जाँची",
    "plan_purchase": "भुगतान को आपके कैश पर परखा",
    "test_move": "एक उपाय को अनुमान पर परखा",
    "get_track_record": "पिछले अनुमान कितने सही रहे, देखा",
    "analyze_expense_changes": "महीने-दर-महीने खर्च की तुलना की",
    "find_unusual_transactions": "असामान्य या दोहरे भुगतान खोजे",
    "get_cash_position": "बैंक बैलेंस जाँचा",
    "get_receivables_and_payables": "उधारी और बकाया जाँचा",
    "get_upcoming_payments": "आने वाले बिल देखे",
    "forecast_cash_flow": "आगे का कैश अनुमान लगाया",
    "simulate_purchase": "ख़रीद को आपके कैश पर परखा",
    "get_supporting_records": "सही रिकॉर्ड निकाले",
    "propose_action": "आपकी मंज़ूरी के लिए काम जोड़ा",
    "get_customers_and_suppliers": "आपका खाता देखा",
    "get_person_details": "उनका खाता खोला",
    "get_health_score": "सेहत स्कोर निकाला",
    "get_weekly_story": "पिछले 7 दिन देखे",
    "get_budgets_and_goals": "बजट और लक्ष्य देखे",
    "get_tax_calendar_and_gst": "GST और टैक्स की तारीख़ें देखीं",
    "run_what_if": "आपके औसत पर हिसाब लगाया",
    "draft_entry": "एंट्री पुष्टि के लिए तैयार की",
    "draft_reminder": "WhatsApp याद-संदेश तैयार किया",
    "draft_goal": "बचत का लक्ष्य तैयार किया",
    "draft_budget": "बजट तैयार किया",
    "update_plan": "योजना अपडेट की",
    "remember": "याद में सेव किया",
    "forget": "याद से हटाया",
    "recall_memory": "आपकी कही बातें देखीं",
    "get_review_queue": "बिना श्रेणी वाली एंट्री देखीं",
    "draft_promise": "वादे का नोट तैयार किया",
    "draft_recategorise": "श्रेणी सुधार तैयार किया",
}
STEP_DOING = {"en": "Working on it", "hi": "काम कर रहा हूँ"}

# Follow-up questions offered after an answer, by the tools it used (English, Hindi).
FOLLOWUPS = {
    "get_receivables_and_payables": [("Remind the most overdue customer", "सबसे पुराने बकाया वाले को याद दिलाओ"), ("Who pays late?", "कौन देर से चुकाता है?")],
    "get_customers_and_suppliers": [("How much does my top customer owe?", "मेरे सबसे बड़े ग्राहक पर कितना बाकी है?"), ("What should I do today?", "आज मुझे क्या करना चाहिए?")],
    "get_person_details": [("Who else owes me money?", "और किस पर उधारी बाकी है?")],
    "get_cash_position": [("When could I run short of cash?", "कैश कब कम पड़ सकता है?"), ("Who owes me money?", "किस पर उधारी बाकी है?")],
    "forecast_cash_flow": [("What if customers pay 30 days late?", "अगर ग्राहक 30 दिन देर से चुकाएँ तो?"), ("Which bills are coming up?", "कौन से बिल आने वाले हैं?")],
    "get_financial_summary": [("Why are my sales less this month?", "इस महीने बिक्री कम क्यों है?"), ("Why did costs go up last month?", "पिछले महीने खर्च क्यों बढ़ा?"), ("Can I raise prices by 5%?", "दाम 5% बढ़ाऊँ तो?")],
    "analyze_expense_changes": [("Any double or unusual payments?", "कोई दोहरा या अजीब भुगतान?"), ("Set budgets from my averages", "मेरे औसत से बजट बताओ")],
    "find_unusual_transactions": [("Show me the biggest costs", "सबसे बड़े खर्च दिखाओ")],
    "get_health_score": [("How can I improve my score?", "स्कोर कैसे सुधारूँ?"), ("How did this week go?", "इस हफ़्ते कैसा रहा?")],
    "get_weekly_story": [("Who are my best customers?", "मेरे सबसे अच्छे ग्राहक कौन हैं?"), ("What's my health score?", "मेरा सेहत स्कोर क्या है?")],
    "run_what_if": [("What if I give a 10% discount for 2 weeks?", "2 हफ़्ते 10% छूट दूँ तो?"), ("Should I hire a helper for ₹15,000?", "₹15,000 पर हेल्पर रखूँ?")],
    "get_tax_calendar_and_gst": [("Which bills are due this month?", "इस महीने कौन से बिल देने हैं?")],
    "get_budgets_and_goals": [("Is my rent too high?", "क्या मेरा किराया ज़्यादा है?")],
    "draft_entry": [("How did this week go?", "इस हफ़्ते कैसा रहा?"), ("Who owes me money?", "किस पर उधारी बाकी है?")],
    "draft_reminder": [("Who else owes me money?", "और किस पर उधारी बाकी है?"), ("Who pays late?", "कौन देर से चुकाता है?")],
    "draft_goal": [("How are my budgets and goals?", "मेरे बजट और लक्ष्य कैसे चल रहे हैं?")],
    "draft_budget": [("How are my budgets and goals?", "मेरे बजट और लक्ष्य कैसे चल रहे हैं?"), ("Help me collect my money", "मेरी उधारी वसूलने में मदद करो")],
    "draft_promise": [("Who else owes me money?", "और किस पर उधारी बाकी है?")],
    "remember": [("What do you remember?", "तुम्हें क्या याद है?")],
    "update_plan": [("Help me collect my money", "मेरी उधारी वसूलने में मदद करो"), ("Help me cut my costs", "मेरा खर्च कम करने में मदद करो")],
    "simulate_purchase": [("What if sales drop 20%?", "अगर बिक्री 20% गिरे तो?"), ("When could I run short of cash?", "कैश कब कम पड़ सकता है?")],
}
STARTERS = [("What should I do today?", "आज मुझे क्या करना चाहिए?"), ("Who owes me money?", "किस पर उधारी बाकी है?"), ("How did this week go?", "इस हफ़्ते कैसा रहा?")]
# Business types: the autopilot works the same for all; the words and examples adapt.
BUSINESS_TYPES = {
    "retail": {"label": "Shop / retail", "customers": "customers", "suppliers": "suppliers"},
    "wholesale": {"label": "Wholesale / distribution", "customers": "buyers", "suppliers": "suppliers"},
    "manufacturing": {"label": "Manufacturing", "customers": "customers", "suppliers": "suppliers"},
    "services": {"label": "Agency / services", "customers": "clients", "suppliers": "vendors"},
    "restaurant": {"label": "Restaurant / café", "customers": "customers", "suppliers": "suppliers"},
    "clinic": {"label": "Clinic / salon / practice", "customers": "patients & clients", "suppliers": "suppliers"},
    "freelance": {"label": "Freelancer / consultant", "customers": "clients", "suppliers": "vendors"},
    "online": {"label": "Online seller", "customers": "marketplaces & buyers", "suppliers": "suppliers"},
}
_LANG: ContextVar[str] = ContextVar("lang", default="en")


def lg() -> str:
    return _LANG.get()


def step_label(tool: str, lang: str | None = None) -> str:
    return (STEP_LABEL_HI if (lang or lg()) == "hi" else STEP_LABEL).get(tool, tool)


def followups(tools: list[str], question: str, lang: str) -> list[str]:
    i = 1 if lang == "hi" else 0
    out: list[str] = []
    for t in dict.fromkeys(tools):
        for pair in FOLLOWUPS.get(t, []):
            if pair[i] not in out and pair[0].lower().rstrip("?") not in question.lower():
                out.append(pair[i])
    if not tools:
        out = [p[i] for p in STARTERS]
    return out[:3]


def create_app(db: Path | None = None, client=None, static_dir: Path | None = STATIC) -> FastAPI:
    db = Path(db or settings().db_path)
    app = FastAPI(title="FinPilot API", docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"], allow_methods=["*"], allow_headers=["*"])
    chats: dict[str, dict] = {}

    @app.middleware("http")
    async def language(request: Request, call_next):
        token = _LANG.set(i18n.norm(request.headers.get("x-lang") or request.query_params.get("lang")))
        try:
            return await call_next(request)
        finally:
            _LANG.reset(token)

    def ds() -> dataset.Dataset:
        return dataset.current(db)

    # ------------------------------------------------------------ state

    @app.get("/api/state")
    def state():
        d = ds()
        up = dataset.raw_upload_tables(db)
        return {
            "business": d.name,
            "source": d.source,
            "is_demo": d.is_demo,
            "as_of": str(d.as_of.date()),
            "as_of_label": views.day_full(d.as_of, lg()),
            "upload": {
                "name": up["name"],
                "bank_rows": 0 if up["ledger"] is None else int(len(up["ledger"])),
                "invoice_rows": 0 if up["obligations"] is None else int(len(up["obligations"])),
                "balance_rows": 0 if up["balances"] is None else int(len(up["balances"])),
                "ready": dataset.uploaded(db) is not None,
            },
            "ai": ai_status(),
            "business_type": _btype(d),
            "type_info": BUSINESS_TYPES.get(_btype(d)),
            "types": [{"key": k, **v} for k, v in BUSINESS_TYPES.items()],
            "demos": [{"key": k, **v, "name": v["name"].replace(" (fictional)", "")} for k, v in dataset.DEMOS.items()],
        }

    def _btype(d: dataset.Dataset) -> str:
        if d.book in dataset.DEMOS:
            return dataset.DEMOS[d.book]["type"]
        return books.settings(db, d.book).get("business_type") or ""

    @app.post("/api/source")
    def set_source(body: dict = Body(...)):
        src = body.get("source")
        if src == "upload" and dataset.uploaded(db) is None:
            raise HTTPException(400, "Upload your bank transactions first.")
        try:
            dataset.set_source(db, src)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        return state()

    # ------------------------------------------------------------ owner views

    @app.get("/api/home")
    def home():
        return views.home(ds(), db, lg())

    @app.get("/api/transactions")
    def transactions(q: str = "", direction: str = "", category: str = "", ids: str = "", limit: int = Query(100, le=500), offset: int = 0):
        return views.transactions(ds(), q, direction, category, [i for i in ids.split(",") if i], limit, offset, lg())

    @app.get("/api/owed")
    def owed():
        return views.owed(ds(), lg())

    @app.get("/api/report")
    def report():
        return views.monthly_report(ds(), lg())

    @app.get("/api/records")
    def records(ids: str = ""):
        return views.records(ds(), [i for i in ids.split(",") if i][:200])

    @app.post("/api/reminder")
    def reminder(body: dict = Body(...)):
        r = khata_views.reminders(ds(), db, str(body.get("lang") or lg()), str(body.get("customer", "")))
        if not r:
            return {"status": "missing", "message": f"Nothing overdue from {body.get('customer', '')}."}
        return {"status": "ok", **r[0]}

    @app.get("/api/forecast")
    def forecast(days: int = Query(90, ge=14, le=365), late_days: int = Query(0, ge=0, le=120), collect_pct: float = Query(100, ge=0, le=100),
                 count_overdue: bool = False, typical: bool = True, cushion: float | None = Query(None, ge=0)):
        return views.forecast(ds(), days, late_days, collect_pct, count_overdue, typical, cushion, lg())

    @app.post("/api/afford")
    def afford(body: dict = Body(...)):
        return views.afford(ds(), body, lg())

    # ------------------------------------------------------------ ask

    def ai_status() -> dict:
        cfg = settings()
        key = cfg.api_key or ""
        var = "GEMINI_API_KEY" if cfg.provider == "gemini" else "ANTHROPIC_API_KEY"
        saved_here = var in config.local_env()
        return {"enabled": cfg.ai_enabled or client is not None, "has_key": bool(key) or client is not None, "paused": cfg.ai_disabled,
                "key_hint": f"…{key[-4:]}" if len(key) > 8 else None, "source": "app" if saved_here else ("environment" if key else None),
                "provider": cfg.provider, "provider_label": "Google Gemini" if cfg.provider == "gemini" else "Anthropic Claude", "model": cfg.active_model}

    def _chat(cid: str | None, d: dataset.Dataset) -> tuple[str, dict]:
        cid = cid or uuid.uuid4().hex
        chat = chats.setdefault(cid, {"messages": [], "results": [], "source": d.source, "actions": {}, "notes": []})
        if chat["source"] != d.source:
            chat.update(messages=[], results=[], source=d.source, actions={}, notes=[])
        return cid, chat

    def _run(question: str, cid: str | None, lang: str, on_event=None) -> dict:
        d = ds()
        cid, chat = _chat(cid, d)
        ctx = ToolContext(d.ledger, d.obligations, d.balances, d.as_of, db, d.book, d.name.replace(" (fictional)", ""), lang)
        preface = ""
        if chat["notes"]:
            preface = "[App note — not typed by the owner] Since your last answer: " + " ".join(chat["notes"])
            chat["notes"] = []
        run = orchestrator.ask(question, ctx, d.name, settings(), client=client, history=chat["messages"], prior_results=chat["results"],
                               lang=lang, on_event=on_event, preface=preface)
        if run.mode == "ai" and run.messages:
            chat["messages"] = run.messages
            chat["results"] += [s.result for s in run.steps]
        store.log(db, "question", question)
        return _package(run, d, lang, question, "chat") | {"conversation_id": cid}

    def _action_out(a: dict) -> dict:
        p = a["payload"]
        return {"id": a["id"], "kind": a["kind"], "title": a["title"], "summary": a["summary"], "preview": a["preview"], "state": a["state"],
                "text": p.get("text"), "whatsapp": p.get("whatsapp"), "phone_saved": p.get("phone_saved"), "result": a.get("result")}

    def _package(run, d: dataset.Dataset, lang: str, question: str, source: str) -> dict:
        seen, ev = set(), []
        for tool, e in run.evidence:
            if tool not in seen:
                seen.add(tool)
                ev.append(views.evidence(e, step_label(tool, lang)))
        for a in run.actions:
            books.save_action(db, d.book, source, a)
        ids = [a["action_id"] for a in run.actions]
        saved = {a["id"]: a for a in books.actions(db, d.book, ids=ids)}
        return {
            "answer": run.answer,
            "mode": run.mode,
            "verified": run.verified,
            "has_figures": any(s.tool not in ("update_plan", "remember", "forget", "recall_memory") for s in run.steps),
            "warnings": run.warnings,
            "steps": [{"label": step_label(s.tool, lang), "tool": s.tool, "ok": s.ok and s.checks_ok, "checks": len(s.checks)} for s in run.steps if s.tool != "update_plan"],
            "plan": run.plan,
            "notes": run.notes,
            "remembered": run.remembered,
            "evidence": ev,
            "actions": [_action_out(saved[i]) for i in ids if i in saved],
            "suggestions": followups([s.tool for s in run.steps], question, lang),
        }

    def _question(body: dict) -> str:
        question = str(body.get("question", "")).strip()
        if not question:
            raise HTTPException(400, "Ask a question.")
        if len(question) > 2000:
            raise HTTPException(400, "Please keep questions under 2,000 characters.")
        return question

    def _logged(question: str, cid: str | None, lang: str, on_event=None, log: bool = True) -> dict:
        d = ds()
        if log:
            books.add_chat(db, d.book, "owner", "text", {"text": question})
        out = _run(question, cid, lang, on_event)
        if log:
            out["chat_id"] = books.add_chat(db, d.book, "munshi", "answer", _stored(out))
        return out

    def _stored(out: dict) -> dict:
        """What the thread keeps of an answer: everything except the full action cards (their live state is read back from the database)."""
        return {k: v for k, v in out.items() if k != "actions"} | {"action_ids": [a["id"] for a in out.get("actions", [])]}

    @app.post("/api/ask")
    def ask(body: dict = Body(...)):
        return _logged(_question(body), body.get("conversation_id"), lg(), log=bool(body.get("log", False)))

    def _stream(work_fn, lang: str) -> StreamingResponse:
        q: queue.Queue = queue.Queue()

        def on_event(e: dict) -> None:
            if e.get("tool"):
                e = {**e, "label": step_label(e["tool"], lang)}
            q.put(e)

        def work() -> None:
            try:
                q.put({"type": "final", "data": work_fn(on_event)})
            except Exception as e:  # never leave the client hanging
                q.put({"type": "error", "message": f"Something went wrong ({type(e).__name__}). Please try again."})

        q.put({"type": "start", "mode": "ai" if ai_status()["enabled"] else "rule-based", "label": STEP_DOING.get(lang, STEP_DOING["en"])})
        threading.Thread(target=work, daemon=True).start()

        def events():
            while True:
                e = q.get()
                yield f"data: {json.dumps(e, default=str, ensure_ascii=False)}\n\n"
                if e["type"] in ("final", "error"):
                    break

        return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.post("/api/ask/stream")
    def ask_stream(body: dict = Body(...)):
        """The same answer as /api/ask, with live progress as server-sent events: plan, step started / finished, the agent's notes, then the final answer."""
        question, cid, lang = _question(body), body.get("conversation_id"), lg()
        log = bool(body.get("log", False))
        return _stream(lambda on_event: _logged(question, cid, lang, on_event, log), lang)

    def _decide(d: dataset.Dataset, action_id: str, decision: str, cid: str | None = None) -> dict:
        """The owner's Confirm / Cancel on a card the agent drafted. Only this — never the model — saves anything."""
        item = books.get_action(db, d.book, action_id)
        if not item or item["state"] == "expired":
            raise HTTPException(404, "This card has expired. Ask again to get a fresh one.")
        if item["state"] != "pending":
            raise HTTPException(409, f"Already {item['state']}.")
        chat = chats.get(str(cid or ""))
        if decision == "cancel":
            books.decide_action(db, d.book, action_id, "cancelled")
            if chat:
                chat["notes"].append(f"The owner cancelled: {item['summary']}.")
            return {"ok": True, "state": "cancelled"}
        p, kind = item["payload"], item["kind"]
        out: dict = {"ok": True, "state": "done"}
        if kind == "record_entry":
            out |= _record_entry(d, p)
            note = f"The owner confirmed and saved: {out['message']} (entry {out['id']})."
        elif kind == "create_goal":
            books.add_goal(db, d.book, p["name"], float(p["target"]), p.get("target_date"), "target", float(p.get("saved") or 0))
            out["message"] = f"Goal saved: {item['summary']}"
            note = f"The owner confirmed the goal: {item['summary']}."
        elif kind == "set_budget":
            books.set_budget(db, d.book, p["category"], float(p["monthly_limit"]))
            out["message"] = f"Budget saved: {item['summary']}"
            note = f"The owner confirmed the budget: {item['summary']}."
        elif kind == "record_promise":
            books.add_promise(db, d.book, p["customer"], float(p.get("amount") or 0), p["date"], p.get("note", ""))
            out["message"] = f"Promise noted: {item['summary']}"
            note = f"The owner confirmed: {item['summary']}."
        elif kind == "recategorise":
            n = _recategorise(d, p["ids"], p["category"], bool(p.get("remember")), p.get("party"))
            out["message"] = f"Updated {n} line(s) to {p['category']}"
            note = f"The owner confirmed: {item['summary']}."
        elif kind == "send_reminder":
            out |= {"message": "Opening WhatsApp — check the message and press send.", "open": p["whatsapp"]}
            note = f"The owner opened WhatsApp to send the reminder to {p['customer']} (FinPilot cannot tell whether it was sent)."
        else:
            raise HTTPException(400, "Unknown action.")
        books.decide_action(db, d.book, action_id, "done", {k: v for k, v in out.items() if k in ("message", "id")})
        if chat:
            chat["notes"].append(note)
        store.log(db, "action_confirmed", f"{kind}: {item['summary']}")
        return out

    @app.post("/api/ask/action/{action_id}")
    def ask_action(action_id: str, body: dict = Body(...)):
        return _decide(ds(), action_id, "cancel" if body.get("decision") == "cancel" else "confirm", body.get("conversation_id"))

    # ------------------------------------------------------------ the agent's own work: daily check-up, inbox, approve all, memory

    def _today() -> str:
        return str(dataset.today().date())

    def _checkup_view(d: dataset.Dataset, c: dict | None) -> dict | None:
        if not c:
            return None
        rows = {a["id"]: a for a in books.actions(db, d.book, ids=c.get("action_ids", []))}
        return {k: v for k, v in c.items() if k != "action_ids"} | {"actions": [_action_out(rows[i]) for i in c.get("action_ids", []) if i in rows]}

    @app.get("/api/agent")
    def agent_state():
        d, lang = ds(), lg()
        c = books.last_checkup(db, d.book, lang)
        return {"checkup": _checkup_view(d, c), "stale": not c or c["day"] != _today(), "today": _today(),
                "pending": len(books.actions(db, d.book, state="pending")), "memory": books.memories(db, d.book), "ai": ai_status()}

    def _run_checkup(lang: str, on_event=None) -> dict:
        d = ds()
        ctx = ToolContext(d.ledger, d.obligations, d.balances, d.as_of, db, d.book, d.name.replace(" (fictional)", ""), lang)
        run = orchestrator.checkup(ctx, d.name, settings(), client=client, lang=lang, on_event=on_event)
        books.expire_actions(db, d.book, "checkup")
        data = _package(run, d, lang, "", "checkup")
        data["action_ids"] = [a["id"] for a in data.pop("actions")]
        books.save_checkup(db, d.book, lang, _today(), data)
        books.add_chat(db, d.book, "munshi", "checkup", data | {"day": _today()})
        store.log(db, "checkup", f"{len(data['action_ids'])} action(s) prepared")
        return _checkup_view(d, books.last_checkup(db, d.book, lang))

    @app.post("/api/agent/checkup")
    def agent_checkup():
        return _run_checkup(lg())

    @app.post("/api/agent/checkup/stream")
    def agent_checkup_stream():
        lang = lg()
        return _stream(lambda on_event: _run_checkup(lang, on_event), lang)

    @app.post("/api/agent/actions/{action_id}")
    def agent_action(action_id: str, body: dict = Body(...)):
        return _decide(ds(), action_id, "cancel" if body.get("decision") == "cancel" else "confirm", body.get("conversation_id"))

    @app.post("/api/agent/approve-all")
    def approve_all(body: dict = Body(...)):
        """Confirm several drafted cards at once. Reminders are left for one-by-one (each opens WhatsApp for the owner to send)."""
        d = ds()
        results = []
        for aid in [str(i) for i in body.get("ids", [])][:20]:
            item = books.get_action(db, d.book, aid)
            if not item or item["state"] != "pending" or item["kind"] == "send_reminder":
                continue
            try:
                results.append({"id": aid, "ok": True, **_decide(ds(), aid, "confirm", body.get("conversation_id"))})
            except HTTPException as e:
                results.append({"id": aid, "ok": False, "message": e.detail})
        return {"done": sum(r["ok"] for r in results), "results": results}

    @app.get("/api/agent/memory")
    def get_memory():
        return books.memories(db, ds().book)

    @app.post("/api/agent/memory")
    def add_memory(body: dict = Body(...)):
        text = str(body.get("text", "")).strip()
        if not text:
            raise HTTPException(400, "Write what I should remember.")
        books.add_memory(db, ds().book, text)
        return books.memories(db, ds().book)

    @app.delete("/api/agent/memory/{memory_id}")
    def delete_memory(memory_id: int):
        books.delete_memory(db, ds().book, memory_id)
        return books.memories(db, ds().book)

    # ------------------------------------------------------------ the cash autopilot

    _AP_CACHE: dict = {}

    def _safety(d: dataset.Dataset) -> float | None:
        v = books.settings(db, d.book).get("safety")
        try:
            return float(v) if v not in (None, "") else None
        except ValueError:
            return None

    def _plan(d: dataset.Dataset) -> tuple[dict, dict[str, str]]:
        states = books.move_states(db, d.book)
        approved = frozenset(k for k, v in states.items() if v in ("approved", "done"))
        outcomes = books.reminder_outcomes(db, d.book)
        coming = _coming(d)
        key = (smart_views._fingerprint(d), _safety(d), approved, tuple(sorted(outcomes.items())), tuple((c["date"], c["amount"], c["label"]) for c in coming))
        if key not in _AP_CACHE:
            if len(_AP_CACHE) > 16:
                _AP_CACHE.clear()
            p = ap.plan(d.ledger, d.balances, d.obligations, d.as_of, safety=_safety(d), approved=approved, outcomes=outcomes,
                        commitments=[{"date": pd.Timestamp(c["date"]), "amount": c["amount"], "label": c["label"], "source": f"event:{c['id']}", "category": "Known event"} for c in coming])
            if p["status"] == "ok":
                p["weekly"] = ap.weekly(timeline_forecast(d, p))
            _AP_CACHE[key] = p
        return copy.deepcopy(_AP_CACHE[key]), states

    def timeline_forecast(d: dataset.Dataset, p: dict) -> dict:
        """The daily forecast behind the timeline: the plan's own forecast (same options, the events the owner told us about)
        with the moves already approved."""
        extra = ap.apply([m for m in p["moves"] if m["approved"] and m["kind"] != "reserve"], d.obligations, d.as_of, ap.Settings())[0]
        extra += [{"date": pd.Timestamp(c["date"]), "amount": c["amount"], "label": c["label"], "source": f"event:{c['id']}", "category": "Known event"} for c in _coming(d)]
        return ap._forecast(d.ledger, d.balances, d.obligations, d.as_of, 91, p["safety"], extra=extra, obl=ap.at_risk(d.obligations, d.as_of)[0])

    @app.get("/api/timeline")
    def timeline(by: str = Query("month", pattern="^(month|quarter)$")):
        """Cash by month or quarter: the past from the ledger, then the forecast (with approved moves)."""
        from finpilot.engine import periods

        d = ds()
        p, _ = _plan(d)
        if p.get("status") != "ok":
            return {"status": p.get("status"), "message": p.get("message", "")}
        r = periods.periods(timeline_forecast(d, p), d.ledger, d.as_of, by)
        return r | {"safety": p["safety"], "plan_basis": p["plan_basis"], "approved": any(m["approved"] for m in p["moves"])}

    def _coming(d: dataset.Dataset) -> list[dict]:
        """Events the owner told FinPilot about that are still ahead (within the 90 days)."""
        end = d.as_of + pd.Timedelta(days=ap.Settings().horizon_days)
        return [e for e in books.events(db, d.book) if d.as_of < pd.Timestamp(e["date"]) <= end]

    @app.get("/api/events")
    def list_events():
        d = ds()
        return {"events": books.events(db, d.book), "today": str(d.as_of.date())}

    @app.post("/api/events")
    def add_event(body: dict = Body(...)):
        """Something the owner knows is coming: festive sales, a big order, a planned purchase. Counted in every forecast and plan."""
        d = ds()
        label = str(body.get("label") or "").strip()[:80]
        if not label:
            raise HTTPException(400, "Say what it is, e.g. 'Diwali sales' or 'New laptop'.")
        try:
            amount = float(body.get("amount"))
        except (TypeError, ValueError) as e:
            raise HTTPException(400, "Enter an amount.") from e
        if amount == 0 or abs(amount) > 1e9:
            raise HTTPException(400, "Enter an amount (money coming in, or going out).")
        if str(body.get("direction", "out")) == "out":
            amount = -abs(amount)
        else:
            amount = abs(amount)
        try:
            when = pd.Timestamp(str(body.get("date")))
        except ValueError as e:
            raise HTTPException(400, "Enter a real date.") from e
        if not d.as_of < when <= d.as_of + pd.Timedelta(days=ap.Settings().horizon_days):
            raise HTTPException(400, "Pick a date within the next 90 days.")
        eid = books.add_event(db, d.book, str(when.date()), amount, label)
        books.log_activity(db, d.book, str(d.as_of.date()), "forecaster", "info",
                           (f"Added to the forecast: {label} ({'+' if amount > 0 else '−'}{views.short(abs(amount))}) on {views.day(when, lg())}." if lg() != "hi"
                            else f"अनुमान में जोड़ा: {label} ({'+' if amount > 0 else '−'}{views.short(abs(amount))}), {views.day(when, lg())}।"))
        return {"id": eid, "events": books.events(db, d.book)}

    @app.delete("/api/events/{event_id}")
    def remove_event(event_id: int):
        d = ds()
        books.delete_event(db, d.book, event_id)
        return {"events": books.events(db, d.book)}

    @app.get("/api/audit.csv")
    def audit_csv():
        """Every agent action and every owner decision, for an accountant or auditor."""
        import csv
        import io

        from fastapi.responses import Response

        d = ds()
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["recorded_at", "book_date", "who", "kind", "what"])
        for r in books.audit(db, d.book):
            w.writerow([r["at"], r["book_date"], r["who"], r["kind"], r["what"]])
        name = re.sub(r"[^a-z0-9]+", "-", d.name.lower()).strip("-") or "finpilot"
        return Response(buf.getvalue().encode("utf-8-sig"), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{name}-audit-log.csv"'})

    def _view(d: dataset.Dataset, lang: str = "en") -> dict:
        def replan(extra=frozenset()):
            if not extra:
                return _plan(d)[0]
            ok = frozenset(k for k, v in books.move_states(db, d.book).items() if v in ("approved", "done")) | extra
            return ap.plan(d.ledger, d.balances, d.obligations, d.as_of, safety=_safety(d), approved=ok,
                           outcomes=books.reminder_outcomes(db, d.book), contingencies=False)

        monitor.check(db, d.book, d.obligations, d.as_of, books.move_states(db, d.book), lang, replan=replan)  # the agents keep watching
        p, states = _plan(d)
        if p["status"] != "ok":
            return p | {"business": d.name.replace(" (fictional)", ""), "is_demo": d.is_demo}
        for m in p["moves"]:
            m["state"] = states.get(m["id"], "open")
        p["moves"] = [m for m in p["moves"] if m["state"] != "dismissed"]
        p["evidence"] = views.evidence(p["evidence"], "How the autopilot works this out")
        # What changed since the books last changed: a small picture is kept per book and compared.
        prev, since = books.snapshot(db, d.book, f"{smart_views._fingerprint(d)}|{_safety(d)}|{[(c['date'], c['amount']) for c in _coming(d)]}", crew.picture(p))
        p["changes"], p["changes_since"] = crew.changes(prev, crew.picture(p), lang), since
        p["headline"] = crew.headline(p, lang)
        p["activity"] = books.activity(db, d.book, 25)
        p["watching"] = [{"move_id": w["move_id"], "party": w["party"], "checkpoint": w["checkpoint"], "kind": w["kind"]} for w in books.watches(db, d.book)]
        p["events"] = _coming(d)
        # the watchtower: what the owner should know before they ask, each with its proof and next steps
        from finpilot.engine import followthrough, investigate, watchtower

        o7 = _outlook(d, 7)
        sc = investigate.sales_change(d.ledger, d.obligations, d.as_of) if len(d.ledger) else None
        p["alerts"] = watchtower.cfo_alerts(p, d.ledger, d.obligations, d.as_of, o7, sc, lang)
        for a_ in p["alerts"]:
            a_["evidence"] = views.evidence(a_["evidence"], a_["title"]) | {"formula": a_["evidence"].get("formula")}
        # approved moves that have left the plan (e.g. the customer paid) are still reported, from their snapshot at approval
        all_states = books.move_states(db, d.book)
        gone = [m | {"state": all_states[i]} for i, m in books.approved_moves(db, d.book).items()
                if all_states.get(i) in ("approved", "done") and i not in {x["id"] for x in p["moves"]}]
        p["follow_through"] = followthrough.follow_through(p["moves"] + gone, books.move_dates(db, d.book), books.watches(db, d.book, None),
                                                           d.ledger, d.obligations, d.as_of, lang)
        p["clock"] = {"date": str(d.as_of.date()), "days_moved": int((d.as_of - pd.Timestamp(dataset.DEMO_AS_OF)).days) if d.is_demo else 0}
        return p | {"business": d.name.replace(" (fictional)", ""), "is_demo": d.is_demo, "business_type": _btype(d), "default_safety": ap.default_safety(d.ledger, d.as_of) if len(d.ledger) else None}

    def _outlook(d: dataset.Dataset, days: int = 14, **kw) -> dict:
        from finpilot.engine import outlook

        states = books.move_states(db, d.book)
        p, _ = _plan(d)
        moves = [m for m in p.get("moves", []) if states.get(m["id"]) in ("approved", "done") and m["kind"] not in ("reserve", "borrow")]
        extra = ap.apply(moves, d.obligations, d.as_of, ap.Settings())[0]
        extra += [{"date": pd.Timestamp(c["date"]), "amount": c["amount"], "label": c["label"], "source": f"event:{c['id']}", "category": "Known event"} for c in _coming(d)]
        covered = frozenset(i for m in moves if m["kind"] == "collect" for i in m["items"])
        r = outlook.outlook(d.ledger, d.balances, ap.at_risk(d.obligations, d.as_of)[0], d.as_of, p.get("safety") or 0.0, days, commitments=extra, covered=covered, **kw)
        if r.get("status") == "ok":
            r["evidence"] = views.evidence(r["evidence"], "How cash in two weeks is worked out")
        return r

    @app.post("/api/outlook")
    def outlook_api(body: dict = Body(default={})):
        """Cash in two weeks under the owner's own assumptions (which collections arrive, bills held, sales level, a planned purchase)."""
        try:
            days = int(body.get("days") or 14)
            sales = float(body.get("sales_pct", 100))
            pur = body.get("purchase") or None
            if pur:
                pur = {"amount": float(pur.get("amount") or 0), "date": str(pur.get("date") or "") or None, "label": str(pur.get("label") or "")}
                if pur["amount"] < 0 or pur["amount"] > 1e10:
                    raise ValueError("amount")
                if pur["date"]:
                    pd.Timestamp(pur["date"])
            skip = tuple(str(x) for x in (body.get("skip") or [])[:200])
            od = tuple(str(x) for x in (body.get("overdue_pay") or [])[:200])
        except (TypeError, ValueError):
            return JSONResponse({"status": "invalid", "message": "Check the amounts and dates."}, status_code=400)
        return _outlook(ds(), days, skip=skip, overdue_pay=od, sales_pct=sales, purchase=pur)

    @app.get("/api/prove")
    def prove(move: str = Query(..., max_length=200)):
        """'Show me why' for one recommendation: its records, the arithmetic, the assumptions and what can't be verified."""
        from finpilot.engine import proof

        d = ds()
        p, _ = _plan(d)
        m = next((x for x in p.get("moves", []) if x["id"] == move), None) if p.get("status") == "ok" else None
        if m is None:
            return JSONResponse({"status": "missing", "message": "That recommendation isn't in the current plan."}, status_code=404)
        r = proof.prove_move(m, p, d.ledger, d.obligations, d.as_of)
        order = {i: k for k, i in enumerate(r["record_ids"])}
        r["records"] = sorted(views.records(d, r["record_ids"][:60]), key=lambda x: order.get(x["id"], 1e9))
        r["record_count"] = len(r["record_ids"])
        return r

    @app.get("/api/autopilot")
    def autopilot():
        return _view(ds(), lg())

    @app.post("/api/crew/stream")
    def crew_stream():
        """The agent crew, live: each agent's finding as it comes, then FinPilot's brief (written by the AI when it is on, and verified)."""
        lang = lg()

        def work(on_event) -> dict:
            d = ds()
            p = _view(d, lang)
            if p["status"] != "ok":
                return {"status": p["status"], "message": p.get("message", "")}
            ai_on = ai_status()["enabled"]
            found = crew.steps(p, lang, ai=ai_on)
            for st in found:
                on_event({"type": "agent", "phase": "start", "agent": st["agent"], "name": st["name"], "doing": st["doing"]})
                time.sleep(0.35)  # pacing so the owner can follow each agent; the work itself is already done
                on_event({"type": "agent", "phase": "done", **st})
            text, mode, verified, warnings = crew.brief(p, lang), "rule-based", True, []
            ctx = ToolContext(d.ledger, d.obligations, d.balances, d.as_of, db, d.book, d.name.replace(" (fictional)", ""), lang)
            if ai_on:
                # The strategist (the language model) proposes ideas beyond the standard moves and must test each with test_move;
                # its report is shown only if every figure in it matches a tool result.
                on_event({"type": "agent", "phase": "start", "agent": "strategist", "name": crew.name("strategist", lang), "doing": crew.doing("strategist", lang)})
                srun = orchestrator.ask(crew.STRATEGIST_QUESTION["hi" if lang == "hi" else "en"], ctx, d.name, settings(), client=client, lang=lang,
                                        on_event=lambda e: on_event({**e, "agent": "strategist"}))
                tested = [s_.result for s_ in srun.steps if s_.tool == "test_move" and isinstance(s_.result, dict) and s_.result.get("status") == "ok"]
                if srun.mode == "ai" and srun.answer and srun.verified:
                    st = {"agent": "strategist", "name": crew.name("strategist", lang), "doing": crew.doing("strategist", lang), "text": srun.answer,
                          "tone": "good" if any(x["verdict"] == "helps" for x in tested) else "info", "ideas": tested}
                else:
                    st = {"agent": "strategist", "name": crew.name("strategist", lang), "doing": crew.doing("strategist", lang), "tone": "info", "ideas": [],
                          "text": "I couldn't verify my ideas against your records this time, so I'm not showing them." if lang != "hi"
                          else "इस बार मैं अपने उपायों को आपके रिकॉर्ड से जाँच नहीं पाया, इसलिए नहीं दिखा रहा।"}
                found.append(st)
                on_event({"type": "agent", "phase": "done", **st})
                on_event({"type": "agent", "phase": "start", "agent": "cfo", "name": "FinPilot", "doing": "Writing your brief…" if lang != "hi" else "आपके लिए सार लिख रहा हूँ…"})
                run = orchestrator.ask(crew.BRIEF_QUESTION["hi" if lang == "hi" else "en"], ctx, d.name, settings(), client=client, lang=lang,
                                       on_event=lambda e: on_event({**e, "agent": "cfo"}))
                if run.mode == "ai" and run.answer and run.verified:
                    text, mode, verified = run.answer, "ai", True
                else:
                    warnings = list(run.warnings)
            books.set_settings(db, d.book, {"crew_last_run": store.now()})
            return {"status": "ok", "steps": found, "brief": text, "mode": mode, "verified": verified, "warnings": warnings,
                    "odds": p["odds"], "suggested": [m["id"] for m in p["moves"] if m["suggested"]]}

        return _stream(work, lang)

    @app.post("/api/demo/fast-forward/stream")
    def fast_forward(body: dict = Body(...)):
        """Demo books only: live the next days as they could happen (engine/live.py), with the agents watching each day."""
        from finpilot.engine import live

        lang = lg()
        d0 = ds()
        if not d0.is_demo:
            raise HTTPException(400, "Fast-forward only works on the demo businesses — it writes simulated days into the books.")
        try:
            days = int(body.get("days", 7))
        except (TypeError, ValueError) as e:
            raise HTTPException(400, "days must be a number") from e
        if not 1 <= days <= 30:
            raise HTTPException(400, "Fast-forward 1 to 30 days at a time.")
        scenario = str(body.get("scenario", "usual"))
        if scenario not in live.SCENARIOS:
            raise HTTPException(400, f"scenario must be one of {', '.join(live.SCENARIOS)}")

        def work(on_event) -> dict:
            d = ds()
            p, states = _plan(d)
            if p.get("status") != "ok":
                return {"status": p.get("status"), "message": p.get("message", "")}
            dates = books.move_dates(db, d.book)
            approved = {m["id"]: m for m in p["moves"] if states.get(m["id"]) in ("approved", "done")}
            lp = live.Plan(safety=p["safety"], learned=p.get("learned", {}))
            for mid, m in approved.items():
                start = pd.Timestamp(dates.get(mid, str(d.as_of.date())))
                if m["kind"] == "collect":
                    lp.reminded[m["party"]] = start
                elif m["kind"] == "pause":
                    lp.paused[m["party"]] = start + pd.Timedelta(days=ap.Settings().pause_days)
                elif m["kind"] == "borrow":
                    lp.overdraft_limit = float(m["amount"])
            try:
                lp.overdraft_drawn = float(books.settings(db, d.book).get("overdraft_drawn") or 0)
            except ValueError:
                lp.overdraft_drawn = 0.0

            def on_day(day, t):
                tmp = dataset.Dataset(d.name, d.book, t.ledger, t.obligations, t.balances, day)
                st = books.move_states(db, d.book)
                ok = frozenset(k for k, v in st.items() if v in ("approved", "done"))

                def replan(extra=frozenset()):
                    return ap.plan(tmp.ledger, tmp.balances, tmp.obligations, day, safety=_safety(d), approved=ok | extra,
                                   outcomes=books.reminder_outcomes(db, d.book), contingencies=False)

                for a in monitor.check(db, d.book, tmp.obligations, day, st, lang, replan=replan):
                    on_event({"type": "activity", **a})

            def emit_days(log):
                for e in log:
                    on_event({"type": "day", **e})

            seed = int(pd.Timestamp(d.as_of).strftime("%j")) + 101 * days
            # live the days one by one so each day's events reach the screen as it is lived
            t = d.tables()
            cur = d.as_of
            for k in range(days):
                t, log = live.advance(t, cur, 1, scenario, lp, seed=seed + k, on_day=on_day)
                cur = cur + pd.Timedelta(days=1)
                for e in log:
                    for it in e["items"]:
                        if it["kind"] == "overdraft":
                            msg = ("Drew {amt} from the standby overdraft to stay above your cushion ({u} of {lim} used)." if lang != "hi"
                                   else "कुशन से ऊपर रहने के लिए स्टैंडबाय ओवरड्राफ़्ट से {amt} लिए ({lim} में से {u} इस्तेमाल)।")
                            text = msg.format(amt=views.short(it["amount"]), u=views.short(it["drawn"]), lim=views.short(it["limit"]))
                            books.log_activity(db, d.book, e["date"], "financing", "caution", text)
                            on_event({"type": "activity", "book_date": e["date"], "agent": "financing", "tone": "caution", "text": text})
                emit_days(log)
                time.sleep(0.15)
            new = dataset.Dataset(d.name, d.book, t.ledger, t.obligations, t.balances, cur)
            dataset.save(db, new, t)
            books.set_settings(db, d.book, {"overdraft_drawn": str(round(lp.overdraft_drawn))})
            v = _view(dataset.current(db), lang)
            return {"status": "ok", "date": str(cur.date()), "headline": v.get("headline"), "changes": v.get("changes", []), "odds": v.get("odds")}

        return _stream(work, lang)

    _TRACK: dict = {}

    @app.get("/api/track-record")
    def track_record():
        """How the forecast and the odds would have done on this business's own past, week by week (engine/backtest.py)."""
        from finpilot.engine import backtest

        d = ds()
        if d.is_demo:  # the demo's original history (simulated days added by fast-forward are not part of its track record)
            key = ("demo", d.book)
            if key not in _TRACK:
                t = dataset._demo_tables(d.book)
                _TRACK[key] = backtest.run(t["ledger"], t["obligations"], t["balances"])
        else:
            key = ("upload", smart_views._fingerprint(d))
            if key not in _TRACK:
                _TRACK[key] = backtest.run(d.ledger, d.obligations, d.balances)
        return _TRACK[key] | {"business": d.name.replace(" (fictional)", ""), "is_demo": d.is_demo}

    @app.post("/api/autopilot/afford")
    def autopilot_afford(body: dict = Body(...)):
        """Can I pay this? Yes / yes if the agents' moves are approved / risky / not now — and the earliest safe day without moves."""
        d = ds()
        try:
            amount = float(body.get("amount"))
        except (TypeError, ValueError) as e:
            raise HTTPException(400, "Enter an amount.") from e
        if amount <= 0:
            raise HTTPException(400, "Enter an amount above zero.")
        when = body.get("date") or None
        try:
            if when is not None:
                pd.Timestamp(when)
        except ValueError as e:
            raise HTTPException(400, "Enter a real date.") from e
        label = str(body.get("label") or "Purchase")[:60]
        states = books.move_states(db, d.book)
        approved = frozenset(k for k, v in states.items() if v in ("approved", "done"))
        coming = [{"date": pd.Timestamp(c["date"]), "amount": c["amount"], "label": c["label"], "source": f"event:{c['id']}", "category": "Known event"} for c in _coming(d)]
        r = ap.afford(d.ledger, d.balances, d.obligations, d.as_of, amount, when, label, safety=_safety(d), approved=approved, commitments=coming)
        if r.get("status") == "ok":
            r["evidence"] = views.evidence(r["evidence"], "How this is worked out")
        return r

    @app.post("/api/autopilot/moves/{move_id:path}")
    def autopilot_move(move_id: str, body: dict = Body(...)):
        """The owner's decision on one move: approve, dismiss, undo, or mark done (e.g. the supplier agreed)."""
        d = ds()
        p, _ = _plan(d)
        m = next((x for x in p.get("moves", []) if x["id"] == move_id), None)
        decision = str(body.get("decision", ""))
        if m is None and decision != "undo":
            raise HTTPException(404, "This move no longer applies — the numbers have changed.")
        out: dict = {"ok": True}
        if decision == "approve":
            books.set_move_state(db, d.book, move_id, "approved")
            monitor.watch_approved(db, d.book, d.as_of, p, m, lg())
            if m["kind"] == "collect":
                r = khata_views.reminders(d, db, lg(), m["party"])
                if r:
                    out |= {"next": "whatsapp", "text": r[0]["text"], "whatsapp": r[0]["whatsapp"]}
            elif m["kind"] == "borrow":
                biz = d.name.replace(" (fictional)", "")
                text = (f"Dear Relationship Manager, {biz} would like to arrange a standby overdraft of {ap.fmt_inr(m['amount'])} against our current account "
                        f"for the next three months, to cover the gap if a large customer payment is delayed. Could you share the terms and documents needed? Thank you.")
                out |= {"next": "copy", "text": text}
            elif m["kind"] == "defer":
                text = (f"Namaste {m['party']} team, could we please pay {m['items'][0]} ({ap.fmt_inr(m['amount'])}) on "
                        f"{pd.Timestamp(m['to_date']):%d %b} instead of {pd.Timestamp(m['from_date']):%d %b}? Thank you for your support. — {d.name.replace(' (fictional)', '')}")
                out |= {"next": "whatsapp", "text": text, "whatsapp": khata_views.whatsapp(text, books.contacts(db, d.book).get(m["party"]))}
        elif decision == "dismiss":
            books.set_move_state(db, d.book, move_id, "dismissed")
            monitor.unwatch(db, d.book, move_id)
        elif decision == "undo":
            books.set_move_state(db, d.book, move_id, None)
            books.set_move_date(db, d.book, move_id, None)
            monitor.unwatch(db, d.book, move_id)
        elif decision == "done":
            if m["kind"] == "defer":  # the supplier agreed: the bill's due date really changes in the books
                obl = d.obligations.copy()
                obl["due_date"] = pd.to_datetime(obl["due_date"])
                obl.loc[obl["item_id"].isin(m["items"]), "due_date"] = pd.Timestamp(m["to_date"])
                dataset.save(db, d, khata.Tables(d.ledger, obl, d.balances))
                books.set_move_state(db, d.book, move_id, None)
            else:
                books.set_move_state(db, d.book, move_id, "done")
        else:
            raise HTTPException(400, "decision must be approve, dismiss, undo or done")
        store.log(db, "autopilot", f"{decision}: {move_id}")
        return out

    @app.post("/api/autopilot/approve-suggested")
    def approve_suggested():
        d = ds()
        p, states = _plan(d)
        ids = [m["id"] for m in p.get("moves", []) if m["suggested"] and states.get(m["id"]) not in ("approved", "done", "dismissed")]
        for m in p.get("moves", []):
            if m["id"] in ids:
                books.set_move_state(db, d.book, m["id"], "approved")
                monitor.watch_approved(db, d.book, d.as_of, p, m, lg())
        return {"approved": ids}

    @app.post("/api/autopilot/plan-b")
    def switch_plan_b():
        """The owner's OK to switch to Plan B: the planner's current best plan for today's books, plus the standby overdraft if it suggests one."""
        d = ds()
        p, states = _plan(d)
        if p.get("status") != "ok":
            raise HTTPException(400, p.get("message", "No plan yet."))
        ids = []
        for m in p["moves"]:
            if (m["suggested"] or m["kind"] == "borrow") and states.get(m["id"]) not in ("approved", "done"):
                books.set_move_state(db, d.book, m["id"], "approved")
                monitor.watch_approved(db, d.book, d.as_of, p, m, lg())
                ids.append(m["id"])
        books.log_activity(db, d.book, str(d.as_of.date()), "planner", "good",
                           "You approved Plan B." if lg() != "hi" else "आपने Plan B मंज़ूर किया।", None)
        return {"approved": ids}

    @app.post("/api/autopilot/safety")
    def autopilot_safety(body: dict = Body(...)):
        d = ds()
        v = body.get("amount")
        if v in (None, ""):
            books.set_settings(db, d.book, {"safety": ""})
        else:
            try:
                x = float(v)
            except (TypeError, ValueError) as e:
                raise HTTPException(400, "Enter an amount.") from e
            if x < 0:
                raise HTTPException(400, "Enter an amount of zero or more.")
            books.set_settings(db, d.book, {"safety": str(round(x))})
        return {"ok": True}

    # ------------------------------------------------------------ the chat thread (Ask) and the cash strip

    def _snapshot(d: dataset.Dataset) -> dict:
        pos = cash_position(d.ledger, d.balances, d.as_of) if len(d.ledger) else {"status": "insufficient_data"}
        obl = obligations_status(d.obligations, d.as_of)
        out = {"cash": pos["cash_balance"] if pos.get("status") == "ok" else None, "as_of_label": views.day_full(d.as_of, lg()),
               "to_collect": 0.0, "collect_overdue": 0.0, "to_pay": 0.0, "pay_overdue": 0.0}
        if obl.get("status") == "ok":
            r, p = obl["receivables"], obl["payables"]
            out |= {"to_collect": round(r["pending_not_due"] + r["overdue"], 2), "collect_overdue": r["overdue"],
                    "to_pay": round(p["pending_not_due"] + p["overdue"], 2), "pay_overdue": p["overdue"]}
        return out

    def _hydrate(d: dataset.Dataset, items: list[dict]) -> list[dict]:
        ids = [i for it in items for i in it["data"].get("action_ids", [])]
        rows = {a["id"]: _action_out(a) for a in books.actions(db, d.book, ids=ids, limit=max(len(ids), 1))} if ids else {}
        for it in items:
            if "action_ids" in it["data"]:
                it["data"]["actions"] = [rows[i] for i in it["data"].pop("action_ids") if i in rows]
        return items

    @app.get("/api/chat")
    def chat():
        d = ds()
        done_today = any((c := books.last_checkup(db, d.book, lang)) and c["day"] == _today() for lang in ("en", "hi"))
        return {"business": d.name.replace(" (fictional)", ""), "is_demo": d.is_demo, "snapshot": _snapshot(d),
                "items": _hydrate(d, books.chat_log(db, d.book)), "checkup_due": not done_today, "ai": ai_status()}

    @app.delete("/api/chat")
    def clear_chat():
        d = ds()
        with books.connect(db) as con:
            con.execute("DELETE FROM chat_log WHERE book = ?", (d.book,))
        chats.pop(f"main:{d.book}", None)
        return {"ok": True}

    # ------------------------------------------------------------ AI settings (the key stays on this computer)

    @app.get("/api/ai")
    def get_ai():
        return ai_status()

    @app.post("/api/ai/key")
    def set_ai_key(body: dict = Body(...)):
        key = str(body.get("key") or "").strip()
        provider = str(body.get("provider") or ("anthropic" if key.startswith("sk-ant-") else "gemini"))
        if provider not in ("gemini", "anthropic"):
            raise HTTPException(400, "Choose Google Gemini or Anthropic Claude.")
        if not body.get("consent"):
            raise HTTPException(400, "Please tick the box to confirm you understand what is sent when AI is on.")
        if any(c.isspace() for c in key) or len(key) < 20:
            raise HTTPException(400, "That doesn't look like an API key. Copy the whole key and try again.")
        if provider == "gemini":
            if key.startswith("sk-ant-"):
                raise HTTPException(400, "That's an Anthropic key — choose Anthropic Claude instead. Gemini keys start with AIza or AQ.")
            ok, why, model = orchestrator.check_gemini_key(key, lg(), os.environ.get("FINPILOT_GEMINI_MODEL"))
            if not ok:
                raise HTTPException(400, f"The key didn't work: {why}.")
            config.save_local("GEMINI_API_KEY", key)
            config.save_local("FINPILOT_GEMINI_MODEL", model)
        else:
            if not key.startswith("sk-ant-"):
                raise HTTPException(400, "That doesn't look like an Anthropic API key (it starts with sk-ant-).")
            ok, why = orchestrator.check_key(key, lg())
            if not ok:
                raise HTTPException(400, f"The key didn't work: {why}.")
            config.save_local("ANTHROPIC_API_KEY", key)
        config.save_local("FINPILOT_PROVIDER", provider)
        config.save_local("FINPILOT_AI", None)
        return ai_status()

    @app.delete("/api/ai/key")
    def remove_ai_key():
        for var in ("GEMINI_API_KEY", "FINPILOT_GEMINI_MODEL", "ANTHROPIC_API_KEY", "FINPILOT_PROVIDER"):
            if var in config.local_env():
                config.save_local(var, None)
        return ai_status()

    @app.post("/api/ai/pause")
    def pause_ai(body: dict = Body(...)):
        config.save_local("FINPILOT_AI", "off" if body.get("paused") else None)
        return ai_status()

    # ------------------------------------------------------------ to-dos (the approval queue)

    @app.get("/api/todos")
    def todos():
        return [
            {"id": a["id"], "text": a["action"], "reason": a["details"].get("reason", ""), "status": {"approved": "done", "rejected": "dismissed"}.get(a["status"], "open"), "created_at": a["created_at"]}
            for a in store.approvals(db)
        ]

    @app.post("/api/todos")
    def add_todo(body: dict = Body(...)):
        text = str(body.get("text", "")).strip()[:200]
        if not text:
            raise HTTPException(400, "Empty to-do.")
        store.propose_action(db, text, {"reason": str(body.get("reason", "Added by you"))[:400]})
        return todos()

    @app.post("/api/todos/{todo_id}")
    def decide_todo(todo_id: int, body: dict = Body(...)):
        decision = {"done": "approved", "dismissed": "rejected"}.get(body.get("status"))
        if decision is None:
            raise HTTPException(400, "status must be done or dismissed")
        try:
            store.decide_action(db, todo_id, decision)
        except KeyError as e:
            raise HTTPException(404, "Not found") from e
        except ValueError as e:
            raise HTTPException(409, str(e)) from e
        return todos()

    # ------------------------------------------------------------ data

    async def _read(file: UploadFile) -> bytes:
        data = await file.read()
        if len(data) > MAX_UPLOAD:
            raise HTTPException(413, "File is larger than 25 MB.")
        if not data:
            raise HTTPException(400, "The file is empty.")
        return data

    def _table(kind: str) -> str:
        if kind not in KINDS:
            raise HTTPException(400, "kind must be bank, invoices or balances")
        return KINDS[kind]

    def _missing(table: str, mapping: dict) -> list[str]:
        return [" or ".join(opts) for opts in REQUIRED[table] if not any(mapping.get(o) for o in opts)]

    @app.post("/api/upload/inspect")
    async def inspect(kind: str = Form(...), file: UploadFile = File(...)):
        table = _table(kind)
        data = await _read(file)
        try:
            raw = loader.read_table(data, file.filename or "upload.csv")
        except Exception as e:  # unreadable file: say so plainly
            raise HTTPException(400, f"Couldn't read this file ({type(e).__name__}). Use CSV or Excel (.xlsx).") from e
        cols = [str(c) for c in raw.columns]
        mapping = loader.suggest_mapping(cols, table)
        preview = raw.head(5).astype(str).replace({"nan": ""}).to_dict(orient="records")
        return {"columns": cols, "fields": loader.TABLE_FIELDS[table], "mapping": mapping, "missing": _missing(table, mapping),
                "rows": int(len(raw)), "preview": preview}

    @app.post("/api/upload/import")
    async def import_file(kind: str = Form(...), file: UploadFile = File(...), mapping: str = Form("{}"), business: str = Form(""),
                          invoice_kind: str = Form(""), incoming_is_sales: str = Form("true"), drop_duplicates: str = Form("false")):
        # form flags parsed by hand: FastAPI versions disagree on how a missing/blank bool form field is read
        def flag(v: str, default: bool) -> bool:
            v = (v or "").strip().lower()
            return default if v == "" else v in ("1", "true", "yes", "on")

        incoming_is_sales, drop_duplicates = flag(incoming_is_sales, True), flag(drop_duplicates, False)
        table = _table(kind)
        data = await _read(file)
        raw = loader.read_table(data, file.filename or "upload.csv")
        try:
            m = {k: v for k, v in json.loads(mapping).items() if v}
        except json.JSONDecodeError as e:
            raise HTTPException(400, "Bad column mapping.") from e
        if not m:
            m = {k: v for k, v in loader.suggest_mapping([str(c) for c in raw.columns], table).items() if v}
        miss = _missing(table, m)
        if miss:
            raise HTTPException(400, "Please choose a column for: " + ", ".join(miss))
        notes = []
        if table == "ledger":
            df, rep = loader.build_ledger(raw, m, drop_exact_duplicates=drop_duplicates)
            if not m.get("category") and len(df):
                df, counts = categorize_ledger(df, books.rules(db, "upload"))
                if not incoming_is_sales:
                    guessed = (df["direction"] == "in") & df["reference"].astype(str).str.contains("auto:guess")
                    df.loc[guessed, "category"] = "Uncategorised"
                sure = counts["high"] + counts["learned"]
                notes.append(f"Sorted {sure} of {len(df)} transactions into categories automatically."
                             + (f" {counts['guess'] + counts['unknown']} need a quick look — open Money → Sort transactions." if counts["guess"] + counts["unknown"] else ""))
        elif table == "obligations":
            dk = {"customers": "receivable", "suppliers": "payable"}.get(invoice_kind)
            df, rep = loader.build_obligations(raw, m, default_kind=dk, default_status="pending" if not m.get("status") else None)
        else:
            df, rep = loader.build_balances(raw, m)
        if not rep.ok:
            raise HTTPException(400, "No usable rows: " + "; ".join(r["reason"] for r in rep.rejected[:3]))
        saved = dataset.save_upload_table(db, table, df, name=business.strip() or None)
        if saved is not None:
            dataset.set_source(db, "upload")
        return {"report": rep.to_dict(), "notes": notes, "summary": _summary(table, df, rep), "state": state()}

    def _summary(table: str, df: pd.DataFrame, rep) -> str:
        n = len(df)
        if table == "ledger":
            d = pd.to_datetime(df["date"])
            s = f"Added {n:,} transactions from {views.day_full(d.min())} to {views.day_full(d.max())}."
        elif table == "obligations":
            s = f"Added {n:,} invoices and bills ({int((df['kind'] == 'receivable').sum())} from customers, {int((df['kind'] == 'payable').sum())} from suppliers)."
        else:
            s = f"Added {n} bank balance{'s' if n != 1 else ''}."
        if rep.rejected:
            s += f" Skipped {len(rep.rejected)} row{'s' if len(rep.rejected) != 1 else ''} we couldn't read."
        if rep.duplicate_groups and table == "ledger":
            s += f" {len(rep.duplicate_groups)} possible duplicate{'s' if len(rep.duplicate_groups) != 1 else ''} kept — ask FinPilot “any double payments?” to review them."
        return s

    @app.post("/api/balance")
    def add_balance(body: dict = Body(...)):
        try:
            when = pd.Timestamp(body["date"]).normalize()
            amount, _ = loader.parse_amount(body["amount"])
        except (KeyError, ValueError) as e:
            raise HTTPException(400, "Enter a date and an amount.") from e
        if amount is None:
            raise HTTPException(400, "Enter the balance as a number.")
        up = dataset.raw_upload_tables(db)
        bal = up["balances"] if up["balances"] is not None else pd.DataFrame(columns=["as_of", "account", "balance"])
        bal = bal[pd.to_datetime(bal["as_of"]) != when] if len(bal) else bal
        bal = pd.concat([bal, pd.DataFrame([{"as_of": when, "account": "Main account", "balance": round(float(amount), 2)}])], ignore_index=True)
        dataset.save_upload_table(db, "balances", bal)
        return state()

    @app.post("/api/as-of")
    def as_of(body: dict = Body(...)):
        if dataset.uploaded(db) is None:
            raise HTTPException(400, "Upload your data first.")
        dataset.set_as_of(db, body["date"])
        return state()

    @app.delete("/api/upload")
    def clear():
        store.clear_dataset(db)
        books.reset_book(db, "upload")
        with store.connect(db) as con:
            con.execute("DELETE FROM meta WHERE key LIKE 'upload:%'")
        dataset.set_source(db, "demo")
        return state()

    @app.post("/api/start")
    def start(body: dict = Body(...)):
        """Start your own book with no files: a name and today's balance."""
        if dataset.uploaded(db) is not None and not body.get("replace"):
            raise HTTPException(409, "You already have your own data. Delete it first to start fresh.")
        bal = body.get("balance")
        amount = None
        if bal not in (None, ""):
            amount, _ = loader.parse_amount(bal)
            if amount is None:
                raise HTTPException(400, "Enter the balance as a number.")
        dataset.start_fresh(db, str(body.get("name") or "My business")[:80], amount, str(dataset.today().date()))
        return state()

    @app.post("/api/demo/reset")
    def reset_demo():
        dataset.reset_demo(db)
        _AP_CACHE.clear()
        return state()

    # ------------------------------------------------------------ khata: quick entries

    def _known_parties(d: dataset.Dataset) -> list[str]:
        names = set(d.ledger["counterparty"].dropna().astype(str))
        if d.obligations is not None and len(d.obligations):
            names |= set(d.obligations["counterparty"].dropna().astype(str))
        return sorted(n for n in names if n and n != "Unknown")

    @app.post("/api/entries/parse")
    def parse_text(body: dict = Body(...)):
        d = ds()
        return parse_entry(str(body.get("text", ""))[:300], d.as_of, _known_parties(d))

    @app.get("/api/entries")
    def recent_entries():
        d = ds()
        return {"entries": books.entries(db, d.book), "parties": _known_parties(d), "categories": khata_views.categories(d),
                "today": str(d.as_of.date())}

    def _record_entry(d: dataset.Dataset, body: dict) -> dict:
        try:
            res = khata.record(d.tables(), str(body.get("kind")), body.get("amount"), body.get("date") or d.as_of,
                               party=str(body.get("party") or ""), category=str(body.get("category") or ""), mode=str(body.get("mode") or "cash"),
                               note=str(body.get("note") or ""), due_date=body.get("due_date") or None, as_of=d.as_of)
        except khata.EntryError as e:
            raise HTTPException(400, str(e)) from e
        dataset.save(db, d, res.tables)
        books.log_entry(db, d.book, res.entry_id, str(body.get("kind")), res.summary, res.undo)
        remaining = None
        if body.get("kind") in ("payment_in", "payment_out") and body.get("party"):
            remaining = khata_views.person(dataset.current(db), db, str(body["party"]))["outstanding"]
            if remaining <= 0 and body.get("kind") == "payment_in":
                books.clear_promise(db, d.book, str(body["party"]))
        msg = res.summary
        if res.settled:
            msg += " · cleared " + ", ".join(f"{s['item_id']}" + ("" if s["full"] else " (part)") for s in res.settled)
        if res.unapplied and body.get("kind") in ("payment_in", "payment_out") and res.settled:
            msg += f" · {views.short(res.unapplied)} more than was due"
        books.add_chat(db, d.book, "event", "entry", {"entry_id": res.entry_id, "entry_kind": str(body.get("kind")), "message": msg,
                                                      "amount": float(body.get("amount") or 0), "party": str(body.get("party") or ""), "undone": False})
        return {"id": res.entry_id, "message": msg, "settled": res.settled, "remaining": remaining,
                "cleared_all": bool(res.settled) and remaining is not None and remaining <= 0}

    @app.post("/api/entries")
    def add_entry(body: dict = Body(...)):
        return _record_entry(ds(), body)

    @app.post("/api/entries/{entry_id}/undo")
    def undo_entry(entry_id: str):
        d = ds()
        rec = books.pop_entry(db, d.book, entry_id)
        if rec is None:
            raise HTTPException(404, "Nothing to undo.")
        dataset.save(db, d, khata.undo(d.tables(), rec))
        books.update_chat_where(db, d.book, "entry", "entry_id", entry_id, {"undone": True})
        return {"ok": True}

    # ------------------------------------------------------------ khata: customers & suppliers

    @app.get("/api/people")
    def people(side: str = "customers"):
        if side not in khata_views.SIDES:
            raise HTTPException(400, "side must be customers or suppliers")
        return khata_views.people(ds(), db, side, lg())

    @app.get("/api/person")
    def person(name: str):
        return khata_views.person(ds(), db, name, lg())

    @app.post("/api/person/contact")
    def contact(body: dict = Body(...)):
        books.set_contact(db, ds().book, str(body["name"]), str(body.get("phone", "")))
        return {"ok": True}

    @app.post("/api/person/promise")
    def promise(body: dict = Body(...)):
        d = ds()
        if body.get("clear"):
            books.clear_promise(db, d.book, str(body["name"]))
        else:
            try:
                when = str(pd.Timestamp(body["date"]).date())
                amt = float(body.get("amount") or 0)
            except (KeyError, ValueError) as e:
                raise HTTPException(400, "Enter a date and amount.") from e
            books.add_promise(db, d.book, str(body["name"]), amt, when, str(body.get("note", ""))[:200])
        return {"ok": True}

    @app.get("/api/reminders")
    def bulk_reminders(customer: str | None = None):
        return khata_views.reminders(ds(), db, lg(), customer)

    # ------------------------------------------------------------ categories

    @app.get("/api/categories")
    def categories():
        return khata_views.categories(ds())

    @app.get("/api/categorise/review")
    def review():
        return khata_views.review(ds(), db)

    def _recategorise(d: dataset.Dataset, ids: list[str], cat: str, remember: bool = False, party: str | None = None) -> int:
        led = d.ledger.copy()
        mask = led["txn_id"].isin(ids)
        led.loc[mask, "category"] = cat
        led.loc[mask, "reference"] = led.loc[mask, "reference"].astype(str).str.replace("auto:guess", "", regex=False).str.strip()
        n = int(mask.sum())
        if remember and party:
            books.set_rule(db, d.book, str(party), cat)
            same = (led["counterparty"].str.lower() == str(party).lower()) & ~mask & led["category"].isin(["Uncategorised", "Sales"]) & led["reference"].astype(str).str.contains("auto:guess")
            led.loc[same, "category"] = cat
            led.loc[same, "reference"] = led.loc[same, "reference"].astype(str).str.replace("auto:guess", "", regex=False).str.strip()
            n += int(same.sum())
        dataset.save(db, d, khata.Tables(led, d.obligations, d.balances))
        return n

    @app.post("/api/categorise")
    def recategorise(body: dict = Body(...)):
        """Set the category for some transactions; optionally remember it for this party."""
        ids = [str(i) for i in body.get("ids", [])]
        cat = str(body.get("category", "")).strip()[:60]
        if not ids or not cat:
            raise HTTPException(400, "Choose transactions and a category.")
        return {"updated": _recategorise(ds(), ids, cat, bool(body.get("remember")), body.get("party"))}

    # ------------------------------------------------------------ smart features

    @app.get("/api/health")
    def health():
        return smart_views.health(ds(), lg())

    @app.get("/api/story")
    def story():
        return smart_views.story(ds(), lg())

    @app.get("/api/budgets")
    def get_budgets():
        return smart_views.budgets(ds(), db, lg())

    @app.post("/api/budgets")
    def set_budgets(body: dict = Body(...)):
        d = ds()
        for cat, limit in (body.get("limits") or {}).items():
            try:
                books.set_budget(db, d.book, str(cat)[:60], float(limit) if limit not in (None, "") else None)
            except ValueError as e:
                raise HTTPException(400, "Budgets must be numbers.") from e
        return smart_views.budgets(ds(), db, lg())

    @app.get("/api/goals")
    def get_goals():
        return smart_views.goals(ds(), db)

    @app.post("/api/goals")
    def add_goal(body: dict = Body(...)):
        try:
            target = float(body["target"])
        except (KeyError, ValueError) as e:
            raise HTTPException(400, "Enter a target amount.") from e
        if target <= 0:
            raise HTTPException(400, "Enter a target amount.")
        books.add_goal(db, ds().book, str(body.get("name") or "My goal")[:60], target, body.get("target_date") or None,
                       str(body.get("icon") or "target")[:20], float(body.get("saved") or 0))
        return smart_views.goals(ds(), db)

    @app.post("/api/goals/{goal_id}")
    def update_goal(goal_id: int, body: dict = Body(...)):
        try:
            add = float(body["add"]) if body.get("add") not in (None, "") else None
        except ValueError as e:
            raise HTTPException(400, "Enter an amount.") from e
        books.update_goal(db, ds().book, goal_id, add=add, delete=bool(body.get("delete")))
        return smart_views.goals(ds(), db)

    @app.get("/api/calendar")
    def calendar(year: int | None = None, month: int | None = None):
        d = ds()
        y, m = year or d.as_of.year, month or d.as_of.month
        if not (1 <= m <= 12 and 2000 <= y <= 2100):
            raise HTTPException(400, "Bad month.")
        return smart_views.calendar(d, db, y, m, lg())

    @app.get("/api/settings")
    def get_settings():
        return books.settings(db, ds().book)

    @app.post("/api/settings")
    def save_settings(body: dict = Body(...)):
        d = ds()
        clean = {}
        for k, v in body.items():
            if k in ("gst_rate_sales", "gst_rate_purchases"):
                try:
                    x = float(v)
                except ValueError as e:
                    raise HTTPException(400, "GST rate must be a number.") from e
                if not 0 <= x <= 28:
                    raise HTTPException(400, "GST rate must be between 0 and 28%.")
                clean[k] = x
            elif k == "gst_filing" and v in ("monthly", "qrmp"):
                clean[k] = v
            elif k == "gst_registered" and v in ("yes", "no"):
                clean[k] = v
            elif k == "language" and v in i18n.LANGS:
                clean[k] = v
            elif k == "business_type" and (v in BUSINESS_TYPES or v == ""):
                clean[k] = v
            elif k == "upi_id":
                v = str(v).strip()
                if v and not re.fullmatch(r"[\w.\-]{2,64}@[A-Za-z][\w]{1,32}", v):
                    raise HTTPException(400, "A UPI ID looks like name@bank.")
                clean[k] = v
        books.set_settings(db, d.book, clean)
        if body.get("business_name") and not d.is_demo:
            raw = dataset.raw_upload_tables(db)
            store.save_dataset(db, str(body["business_name"])[:80], {k: raw[k] for k in store.TABLES}, raw["as_of"] or str(d.as_of.date()), book="upload")
        return books.settings(db, d.book)

    @app.get("/api/whatif/{kind}")
    def what_if(kind: str, request: Request):
        return smart_views.whatifs(ds(), kind, dict(request.query_params), lg())

    @app.get("/api/reports/months")
    def report_months():
        return smart_views.months_available(ds(), lg())

    @app.get("/api/reports/monthly")
    def report_monthly(month: str = ""):
        d = ds()
        try:
            p = pd.Period(month or str(d.as_of.to_period("M")), "M")
        except ValueError as e:
            raise HTTPException(400, "Month must be YYYY-MM.") from e
        return smart_views.report_monthly(d, db, p.year, p.month, lg())

    @app.get("/api/reports/loan")
    def report_loan():
        return smart_views.report_loan(ds(), lg())

    if static_dir is not None and Path(static_dir).exists():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="web")
    return app
