"""
HTTP API for the FinPilot web app, plus the built front end. Runs locally; nothing is sent anywhere
except, in AI mode, the question and tool outputs to Anthropic's API (see README).
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pandas as pd
from fastapi import Body, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from finpilot.agent import orchestrator
from finpilot.agent.tools import ToolContext
from finpilot.config import settings
from finpilot.data import loader, store

from . import dataset, views

STATIC = Path(__file__).resolve().parents[1] / "web"
MAX_UPLOAD = 25 * 1024 * 1024

KINDS = {"bank": "ledger", "invoices": "obligations", "balances": "balances"}
REQUIRED = {"ledger": [("date",), ("amount", "debit", "credit")], "obligations": [("amount",), ("due_date",)], "balances": [("as_of",), ("balance",)]}

STEP_LABEL = {
    "get_financial_summary": "Worked out sales, costs and profit",
    "analyze_expense_changes": "Compared your costs month to month",
    "find_unusual_transactions": "Looked for unusual or double payments",
    "get_cash_position": "Checked your bank balance",
    "get_receivables_and_payables": "Checked who owes you and what you owe",
    "get_upcoming_payments": "Looked at bills coming up",
    "forecast_cash_flow": "Projected your cash ahead",
    "simulate_purchase": "Tested the purchase against your cash",
    "get_supporting_records": "Pulled up the exact records",
    "propose_action": "Added a to-do for you to approve",
}


def create_app(db: Path | None = None, client=None, static_dir: Path | None = STATIC) -> FastAPI:
    cfg = settings()
    db = Path(db or cfg.db_path)
    app = FastAPI(title="FinPilot API", docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"], allow_methods=["*"], allow_headers=["*"])
    chats: dict[str, dict] = {}

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
            "as_of_label": views.day_full(d.as_of),
            "upload": {
                "name": up["name"],
                "bank_rows": 0 if up["ledger"] is None else int(len(up["ledger"])),
                "invoice_rows": 0 if up["obligations"] is None else int(len(up["obligations"])),
                "balance_rows": 0 if up["balances"] is None else int(len(up["balances"])),
                "ready": up["ledger"] is not None and len(up["ledger"]) > 0,
            },
            "ai": {"enabled": cfg.ai_enabled or client is not None, "model": cfg.model},
        }

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
        return views.home(ds())

    @app.get("/api/transactions")
    def transactions(q: str = "", direction: str = "", category: str = "", ids: str = "", limit: int = Query(100, le=500), offset: int = 0):
        return views.transactions(ds(), q, direction, category, [i for i in ids.split(",") if i], limit, offset)

    @app.get("/api/owed")
    def owed():
        return views.owed(ds())

    @app.get("/api/report")
    def report():
        return views.monthly_report(ds())

    @app.get("/api/records")
    def records(ids: str = ""):
        return views.records(ds(), [i for i in ids.split(",") if i][:200])

    @app.post("/api/reminder")
    def reminder(body: dict = Body(...)):
        return views.reminder(ds(), str(body.get("customer", "")))

    @app.get("/api/forecast")
    def forecast(days: int = Query(90, ge=14, le=365), late_days: int = Query(0, ge=0, le=120), collect_pct: float = Query(100, ge=0, le=100),
                 count_overdue: bool = False, typical: bool = True, cushion: float | None = Query(None, ge=0)):
        return views.forecast(ds(), days, late_days, collect_pct, count_overdue, typical, cushion)

    @app.post("/api/afford")
    def afford(body: dict = Body(...)):
        return views.afford(ds(), body)

    # ------------------------------------------------------------ ask

    @app.post("/api/ask")
    def ask(body: dict = Body(...)):
        question = str(body.get("question", "")).strip()
        if not question:
            raise HTTPException(400, "Ask a question.")
        if len(question) > 2000:
            raise HTTPException(400, "Please keep questions under 2,000 characters.")
        d = ds()
        cid = body.get("conversation_id") or uuid.uuid4().hex
        chat = chats.setdefault(cid, {"messages": [], "results": [], "source": d.source})
        if chat["source"] != d.source:
            chat.update(messages=[], results=[], source=d.source)
        ctx = ToolContext(d.ledger, d.obligations, d.balances, d.as_of, db)
        run = orchestrator.ask(question, ctx, d.name, cfg, client=client, history=chat["messages"], prior_results=chat["results"])
        if run.mode == "ai" and run.messages:
            chat["messages"] = run.messages
            chat["results"] += [s.result for s in run.steps]
        store.log(db, "question", question)
        seen, ev = set(), []
        for tool, e in run.evidence:
            if tool not in seen:
                seen.add(tool)
                ev.append(views.evidence(e, STEP_LABEL.get(tool, tool)))
        return {
            "conversation_id": cid,
            "answer": run.answer,
            "mode": run.mode,
            "verified": run.verified,
            "has_figures": bool(run.steps),
            "warnings": run.warnings,
            "steps": [{"label": STEP_LABEL.get(s.tool, s.tool), "ok": s.ok and s.checks_ok, "checks": len(s.checks)} for s in run.steps],
            "evidence": ev,
        }

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
                          invoice_kind: str = Form(""), incoming_is_sales: bool = Form(True), drop_duplicates: bool = Form(False)):
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
            if not m.get("category") and incoming_is_sales and len(df):
                mask = (df["direction"] == "in") & (df["category"] == "Uncategorised")
                df.loc[mask, "category"] = "Sales"
                if mask.any():
                    notes.append(f"{int(mask.sum())} incoming payments were counted as sales (your file has no category column). Untick this if some are loans or transfers.")
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
            s += f" {len(rep.duplicate_groups)} possible duplicate{'s' if len(rep.duplicate_groups) != 1 else ''} kept — check them on Home."
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
        dataset.set_source(db, "demo")
        return state()

    if static_dir is not None and Path(static_dir).exists():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="web")
    return app
