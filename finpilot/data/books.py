"""
Book-scoped records the owner creates in the app: contacts, payment promises, category rules,
budgets, savings goals, settings, and an undo log for quick entries. Everything is local SQLite.

A "book" is "demo" (the fictional shop, editable and resettable) or "upload" (the owner's data).
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from finpilot.data import store

SCHEMA = [
    "CREATE TABLE IF NOT EXISTS contacts (book TEXT, name TEXT, phone TEXT, PRIMARY KEY (book, name))",
    "CREATE TABLE IF NOT EXISTS promises (id INTEGER PRIMARY KEY AUTOINCREMENT, book TEXT, party TEXT, amount REAL, date TEXT, note TEXT, created_at TEXT)",
    "CREATE TABLE IF NOT EXISTS cat_rules (book TEXT, match TEXT, category TEXT, PRIMARY KEY (book, match))",
    "CREATE TABLE IF NOT EXISTS budgets (book TEXT, category TEXT, monthly_limit REAL, PRIMARY KEY (book, category))",
    "CREATE TABLE IF NOT EXISTS goals (id INTEGER PRIMARY KEY AUTOINCREMENT, book TEXT, name TEXT, target REAL, saved REAL, target_date TEXT, icon TEXT, created_at TEXT)",
    "CREATE TABLE IF NOT EXISTS settings (book TEXT, key TEXT, value TEXT, PRIMARY KEY (book, key))",
    "CREATE TABLE IF NOT EXISTS entry_log (id TEXT, book TEXT, at TEXT, kind TEXT, summary TEXT, undo TEXT, undone INTEGER DEFAULT 0, PRIMARY KEY (book, id))",
    "CREATE TABLE IF NOT EXISTS agent_actions (id TEXT, book TEXT, created_at TEXT, source TEXT, kind TEXT, title TEXT, summary TEXT, payload TEXT, "
    "preview TEXT, state TEXT, decided_at TEXT, result TEXT, PRIMARY KEY (book, id))",
    "CREATE TABLE IF NOT EXISTS memory (id INTEGER PRIMARY KEY AUTOINCREMENT, book TEXT, text TEXT, created_at TEXT)",
    "CREATE TABLE IF NOT EXISTS checkups (book TEXT, lang TEXT, day TEXT, ran_at TEXT, data TEXT, PRIMARY KEY (book, lang))",
    "CREATE TABLE IF NOT EXISTS autopilot_moves (book TEXT, id TEXT, state TEXT, at TEXT, PRIMARY KEY (book, id))",
    "CREATE TABLE IF NOT EXISTS autopilot_snapshots (id INTEGER PRIMARY KEY AUTOINCREMENT, book TEXT, at TEXT, fingerprint TEXT, data TEXT)",
    "CREATE TABLE IF NOT EXISTS watches (id INTEGER PRIMARY KEY AUTOINCREMENT, book TEXT, move_id TEXT, kind TEXT, party TEXT, items TEXT, "
    "amount REAL, started TEXT, checkpoint TEXT, plan_b TEXT, status TEXT, resolved TEXT)",
    "CREATE TABLE IF NOT EXISTS agent_activity (id INTEGER PRIMARY KEY AUTOINCREMENT, book TEXT, book_date TEXT, at TEXT, agent TEXT, tone TEXT, text TEXT, action TEXT)",
    "CREATE TABLE IF NOT EXISTS reminder_outcomes (id INTEGER PRIMARY KEY AUTOINCREMENT, book TEXT, party TEXT, sent_on TEXT, result TEXT, resolved_on TEXT)",
    "CREATE TABLE IF NOT EXISTS move_dates (book TEXT, id TEXT, book_date TEXT, PRIMARY KEY (book, id))",
    "CREATE TABLE IF NOT EXISTS approved_moves (book TEXT, id TEXT, data TEXT, PRIMARY KEY (book, id))",
    "CREATE TABLE IF NOT EXISTS known_events (id INTEGER PRIMARY KEY AUTOINCREMENT, book TEXT, date TEXT, amount REAL, label TEXT, created_at TEXT)",
    "CREATE TABLE IF NOT EXISTS chat_log (id INTEGER PRIMARY KEY AUTOINCREMENT, book TEXT, at TEXT, role TEXT, kind TEXT, data TEXT)",
]


@contextmanager
def connect(path: Path):
    with store.connect(path) as con:
        for q in SCHEMA:
            con.execute(q)
        yield con


def _rows(cur: sqlite3.Cursor) -> list[dict]:
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


# ---------------------------------------------------------------- contacts


def contacts(db: Path, book: str) -> dict[str, str]:
    with connect(db) as con:
        return dict(con.execute("SELECT name, phone FROM contacts WHERE book = ?", (book,)).fetchall())


def set_contact(db: Path, book: str, name: str, phone: str) -> None:
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) == 10:
        digits = "91" + digits  # Indian mobile without country code
    with connect(db) as con:
        con.execute("INSERT OR REPLACE INTO contacts VALUES (?, ?, ?)", (book, name, digits))


# ---------------------------------------------------------------- promises to pay


def promises(db: Path, book: str) -> list[dict]:
    with connect(db) as con:
        return _rows(con.execute("SELECT id, party, amount, date, note, created_at FROM promises WHERE book = ? ORDER BY date", (book,)))


def add_promise(db: Path, book: str, party: str, amount: float, date: str, note: str = "") -> None:
    with connect(db) as con:
        con.execute("DELETE FROM promises WHERE book = ? AND party = ?", (book, party))  # one live promise per customer
        con.execute("INSERT INTO promises (book, party, amount, date, note, created_at) VALUES (?, ?, ?, ?, ?, ?)", (book, party, amount, date, note, store.now()))


def clear_promise(db: Path, book: str, party: str) -> None:
    with connect(db) as con:
        con.execute("DELETE FROM promises WHERE book = ? AND party = ?", (book, party))


# ---------------------------------------------------------------- category rules


def rules(db: Path, book: str) -> dict[str, str]:
    with connect(db) as con:
        return dict(con.execute("SELECT match, category FROM cat_rules WHERE book = ?", (book,)).fetchall())


def set_rule(db: Path, book: str, match: str, category: str) -> None:
    with connect(db) as con:
        con.execute("INSERT OR REPLACE INTO cat_rules VALUES (?, ?, ?)", (book, match.strip().lower(), category))


# ---------------------------------------------------------------- budgets and goals


def budgets(db: Path, book: str) -> dict[str, float]:
    with connect(db) as con:
        return {c: float(v) for c, v in con.execute("SELECT category, monthly_limit FROM budgets WHERE book = ?", (book,)).fetchall()}


def set_budget(db: Path, book: str, category: str, limit: float | None) -> None:
    with connect(db) as con:
        if not limit:
            con.execute("DELETE FROM budgets WHERE book = ? AND category = ?", (book, category))
        else:
            con.execute("INSERT OR REPLACE INTO budgets VALUES (?, ?, ?)", (book, category, float(limit)))


def goals(db: Path, book: str) -> list[dict]:
    with connect(db) as con:
        return _rows(con.execute("SELECT id, name, target, saved, target_date, icon, created_at FROM goals WHERE book = ? ORDER BY id", (book,)))


def add_goal(db: Path, book: str, name: str, target: float, target_date: str | None, icon: str = "target", saved: float = 0.0) -> int:
    with connect(db) as con:
        cur = con.execute("INSERT INTO goals (book, name, target, saved, target_date, icon, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                          (book, name, target, saved, target_date, icon, store.now()))
        return int(cur.lastrowid)


def update_goal(db: Path, book: str, goal_id: int, add: float | None = None, delete: bool = False) -> None:
    with connect(db) as con:
        if delete:
            con.execute("DELETE FROM goals WHERE book = ? AND id = ?", (book, goal_id))
        elif add is not None:
            con.execute("UPDATE goals SET saved = MAX(0, saved + ?) WHERE book = ? AND id = ?", (add, book, goal_id))


# ---------------------------------------------------------------- settings


DEFAULT_SETTINGS = {"gst_registered": "yes", "gst_rate_sales": "5", "gst_rate_purchases": "5", "gst_filing": "monthly", "language": "en",
                    "business_type": "", "safety": "", "crew_last_run": "", "overdraft_drawn": "", "upi_id": ""}


def settings(db: Path, book: str) -> dict[str, str]:
    with connect(db) as con:
        got = dict(con.execute("SELECT key, value FROM settings WHERE book = ?", (book,)).fetchall())
    return DEFAULT_SETTINGS | got


def set_settings(db: Path, book: str, values: dict) -> None:
    with connect(db) as con:
        for k, v in values.items():
            if k in DEFAULT_SETTINGS:
                con.execute("INSERT OR REPLACE INTO settings VALUES (?, ?, ?)", (book, k, str(v)))


# ---------------------------------------------------------------- entry log (undo)


def log_entry(db: Path, book: str, entry_id: str, kind: str, summary: str, undo: dict) -> None:
    with connect(db) as con:
        con.execute("INSERT OR REPLACE INTO entry_log (id, book, at, kind, summary, undo, undone) VALUES (?, ?, ?, ?, ?, ?, 0)",
                    (entry_id, book, store.now(), kind, summary, json.dumps(undo, default=str)))


def entries(db: Path, book: str, limit: int = 30) -> list[dict]:
    with connect(db) as con:
        return _rows(con.execute("SELECT id, at, kind, summary, undone FROM entry_log WHERE book = ? ORDER BY at DESC, id DESC LIMIT ?", (book, limit)))


def pop_entry(db: Path, book: str, entry_id: str) -> dict | None:
    with connect(db) as con:
        row = con.execute("SELECT undo, undone FROM entry_log WHERE book = ? AND id = ?", (book, entry_id)).fetchone()
        if not row or row[1]:
            return None
        con.execute("UPDATE entry_log SET undone = 1 WHERE book = ? AND id = ?", (book, entry_id))
        return json.loads(row[0])


def reset_book(db: Path, book: str) -> None:
    """Forget everything the owner did in a book (used for 'Reset demo')."""
    with connect(db) as con:
        for t in ("contacts", "promises", "cat_rules", "budgets", "goals", "settings", "entry_log", "agent_actions", "memory", "checkups", "chat_log", "autopilot_moves", "autopilot_snapshots",
                  "watches", "agent_activity", "reminder_outcomes", "move_dates", "approved_moves", "known_events"):
            con.execute(f"DELETE FROM {t} WHERE book = ?", (book,))


# ---------------------------------------------------------------- agent: drafted actions (owner confirms), memory, daily check-ups


def save_action(db: Path, book: str, source: str, a: dict) -> None:
    with connect(db) as con:
        con.execute("INSERT OR REPLACE INTO agent_actions (id, book, created_at, source, kind, title, summary, payload, preview, state, decided_at, result) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', NULL, NULL)",
                    (a["action_id"], book, store.now(), source, a["action"], a["title"], a["summary"], json.dumps(a["payload"], default=str),
                     json.dumps(a.get("preview") or {}, default=str)))


def _action_row(r: dict) -> dict:
    return r | {"payload": json.loads(r["payload"] or "{}"), "preview": json.loads(r["preview"] or "{}"), "result": json.loads(r["result"]) if r.get("result") else None}


def get_action(db: Path, book: str, action_id: str) -> dict | None:
    with connect(db) as con:
        rows = _rows(con.execute("SELECT * FROM agent_actions WHERE book = ? AND id = ?", (book, action_id)))
    return _action_row(rows[0]) if rows else None


def actions(db: Path, book: str, ids: list[str] | None = None, state: str | None = None, source: str | None = None, limit: int = 50) -> list[dict]:
    q, args = "SELECT * FROM agent_actions WHERE book = ?", [book]
    if ids is not None:
        q += f" AND id IN ({','.join('?' * len(ids))})" if ids else " AND 0"
        args += ids
    if state:
        q += " AND state = ?"
        args.append(state)
    if source:
        q += " AND source = ?"
        args.append(source)
    with connect(db) as con:
        return [_action_row(r) for r in _rows(con.execute(q + " ORDER BY created_at DESC LIMIT ?", (*args, limit)))]


def decide_action(db: Path, book: str, action_id: str, state: str, result: dict | None = None) -> None:
    with connect(db) as con:
        con.execute("UPDATE agent_actions SET state = ?, decided_at = ?, result = ? WHERE book = ? AND id = ?",
                    (state, store.now(), json.dumps(result, default=str) if result else None, book, action_id))


def expire_actions(db: Path, book: str, source: str) -> None:
    """Older pending drafts from a source (e.g. yesterday's check-up) are replaced by the new run's."""
    with connect(db) as con:
        con.execute("UPDATE agent_actions SET state = 'expired', decided_at = ? WHERE book = ? AND source = ? AND state = 'pending'", (store.now(), book, source))


def memories(db: Path, book: str) -> list[dict]:
    with connect(db) as con:
        return _rows(con.execute("SELECT id, text, created_at FROM memory WHERE book = ? ORDER BY id", (book,)))


def add_memory(db: Path, book: str, text: str) -> int:
    text = " ".join(str(text).split())[:300]
    with connect(db) as con:
        dup = con.execute("SELECT id FROM memory WHERE book = ? AND lower(text) = lower(?)", (book, text)).fetchone()
        if dup:
            return int(dup[0])
        return int(con.execute("INSERT INTO memory (book, text, created_at) VALUES (?, ?, ?)", (book, text, store.now())).lastrowid)


def delete_memory(db: Path, book: str, memory_id: int) -> bool:
    with connect(db) as con:
        return con.execute("DELETE FROM memory WHERE book = ? AND id = ?", (book, memory_id)).rowcount > 0


def save_checkup(db: Path, book: str, lang: str, day: str, data: dict) -> None:
    with connect(db) as con:
        con.execute("INSERT OR REPLACE INTO checkups (book, lang, day, ran_at, data) VALUES (?, ?, ?, ?, ?)", (book, lang, day, store.now(), json.dumps(data, default=str)))


def last_checkup(db: Path, book: str, lang: str) -> dict | None:
    with connect(db) as con:
        r = con.execute("SELECT day, ran_at, data FROM checkups WHERE book = ? AND lang = ?", (book, lang)).fetchone()
    return {"day": r[0], "ran_at": r[1], **json.loads(r[2])} if r else None


# ---------------------------------------------------------------- the chat thread (the owner's messages, Munshi's replies, and khata events)


def add_chat(db: Path, book: str, role: str, kind: str, data: dict) -> int:
    with connect(db) as con:
        return int(con.execute("INSERT INTO chat_log (book, at, role, kind, data) VALUES (?, ?, ?, ?, ?)",
                               (book, store.now(), role, kind, json.dumps(data, default=str))).lastrowid)


def chat_log(db: Path, book: str, limit: int = 150) -> list[dict]:
    with connect(db) as con:
        rows = _rows(con.execute("SELECT id, at, role, kind, data FROM chat_log WHERE book = ? ORDER BY id DESC LIMIT ?", (book, limit)))
    return [r | {"data": json.loads(r["data"])} for r in reversed(rows)]


def update_chat_where(db: Path, book: str, kind: str, key: str, value, changes: dict) -> None:
    """Merge `changes` into chat items of a kind whose data[key] == value (e.g. mark an entry event undone)."""
    with connect(db) as con:
        for i, d in con.execute("SELECT id, data FROM chat_log WHERE book = ? AND kind = ?", (book, kind)).fetchall():
            data = json.loads(d)
            if data.get(key) == value:
                con.execute("UPDATE chat_log SET data = ? WHERE id = ?", (json.dumps(data | changes, default=str), i))


# ---------------------------------------------------------------- cash autopilot: the owner's decisions on the agents' moves


def move_states(db: Path, book: str) -> dict[str, str]:
    with connect(db) as con:
        return dict(con.execute("SELECT id, state FROM autopilot_moves WHERE book = ?", (book,)).fetchall())


def set_move_state(db: Path, book: str, move_id: str, state: str | None) -> None:
    with connect(db) as con:
        if state is None:
            con.execute("DELETE FROM autopilot_moves WHERE book = ? AND id = ?", (book, move_id))
        else:
            con.execute("INSERT OR REPLACE INTO autopilot_moves VALUES (?, ?, ?, ?)", (book, move_id, state, store.now()))


def snapshot(db: Path, book: str, fingerprint: str, data: dict) -> tuple[dict | None, str | None]:
    """Save this picture of the cash plan if the books changed since the last one. Returns the previous picture and when it was taken."""
    with connect(db) as con:
        rows = con.execute("SELECT at, fingerprint, data FROM autopilot_snapshots WHERE book = ? ORDER BY id DESC LIMIT 2", (book,)).fetchall()
        if not rows or rows[0][1] != fingerprint:
            con.execute("INSERT INTO autopilot_snapshots (book, at, fingerprint, data) VALUES (?, ?, ?, ?)", (book, store.now(), fingerprint, json.dumps(data)))
            con.execute("DELETE FROM autopilot_snapshots WHERE book = ? AND id NOT IN (SELECT id FROM autopilot_snapshots WHERE book = ? ORDER BY id DESC LIMIT 2)", (book, book))
            prev = rows[0] if rows else None
        else:
            prev = rows[1] if len(rows) > 1 else None
    return (json.loads(prev[2]), prev[0]) if prev else (None, None)


# ---------------------------------------------------------------- the agents' watch list, activity log and what they learned


def add_watch(db: Path, book: str, move: dict, started: str, checkpoint: str, plan_b: dict | None) -> None:
    with connect(db) as con:
        con.execute("DELETE FROM watches WHERE book = ? AND move_id = ? AND status = 'open'", (book, move["id"]))
        con.execute("INSERT INTO watches (book, move_id, kind, party, items, amount, started, checkpoint, plan_b, status) VALUES (?,?,?,?,?,?,?,?,?, 'open')",
                    (book, move["id"], move["kind"], move.get("party", ""), json.dumps(move.get("items", [])), float(move.get("amount", 0)), started, checkpoint,
                     json.dumps(plan_b) if plan_b else None))


def drop_watch(db: Path, book: str, move_id: str) -> None:
    with connect(db) as con:
        con.execute("DELETE FROM watches WHERE book = ? AND move_id = ? AND status = 'open'", (book, move_id))


def watches(db: Path, book: str, status: str | None = "open") -> list[dict]:
    with connect(db) as con:
        q = "SELECT id, move_id, kind, party, items, amount, started, checkpoint, plan_b, status, resolved FROM watches WHERE book = ?"
        rows = con.execute(q + (" AND status = ?" if status else "") + " ORDER BY id", (book, status) if status else (book,)).fetchall()
    keys = ("id", "move_id", "kind", "party", "items", "amount", "started", "checkpoint", "plan_b", "status", "resolved")
    out = []
    for r in rows:
        w = dict(zip(keys, r))
        w["items"] = json.loads(w["items"] or "[]")
        w["plan_b"] = json.loads(w["plan_b"]) if w["plan_b"] else None
        out.append(w)
    return out


def close_watch(db: Path, book: str, watch_id: int, status: str, resolved: str) -> None:
    with connect(db) as con:
        con.execute("UPDATE watches SET status = ?, resolved = ? WHERE book = ? AND id = ?", (status, resolved, book, watch_id))


def log_activity(db: Path, book: str, book_date: str, agent: str, tone: str, text: str, action: dict | None = None) -> None:
    with connect(db) as con:
        con.execute("INSERT INTO agent_activity (book, book_date, at, agent, tone, text, action) VALUES (?,?,?,?,?,?,?)",
                    (book, book_date, store.now(), agent, tone, text, json.dumps(action) if action else None))


def activity(db: Path, book: str, limit: int = 30) -> list[dict]:
    with connect(db) as con:
        rows = con.execute("SELECT id, book_date, at, agent, tone, text, action FROM agent_activity WHERE book = ? ORDER BY id DESC LIMIT ?", (book, limit)).fetchall()
    return [{"id": r[0], "book_date": r[1], "at": r[2], "agent": r[3], "tone": r[4], "text": r[5], "action": json.loads(r[6]) if r[6] else None} for r in rows]


def note_reminder(db: Path, book: str, party: str, sent_on: str) -> None:
    with connect(db) as con:
        if not con.execute("SELECT 1 FROM reminder_outcomes WHERE book = ? AND party = ? AND result IS NULL", (book, party)).fetchone():
            con.execute("INSERT INTO reminder_outcomes (book, party, sent_on) VALUES (?,?,?)", (book, party, sent_on))


def resolve_reminder(db: Path, book: str, party: str, result: str, on: str) -> None:
    with connect(db) as con:
        con.execute("UPDATE reminder_outcomes SET result = ?, resolved_on = ? WHERE book = ? AND party = ? AND result IS NULL", (result, on, book, party))


def reminder_outcomes(db: Path, book: str) -> dict[str, tuple[int, int]]:
    """Per customer: (reminders whose outcome is known, of which paid)."""
    with connect(db) as con:
        rows = con.execute("SELECT party, COUNT(*), SUM(result = 'paid') FROM reminder_outcomes WHERE book = ? AND result IS NOT NULL GROUP BY party", (book,)).fetchall()
    return {r[0]: (int(r[1]), int(r[2] or 0)) for r in rows}


def set_move_date(db: Path, book: str, move_id: str, book_date: str | None, move: dict | None = None) -> None:
    """When a move was approved — and what it was then, so its outcome can be reported after it leaves the plan."""
    with connect(db) as con:
        if book_date is None:
            con.execute("DELETE FROM move_dates WHERE book = ? AND id = ?", (book, move_id))
            con.execute("DELETE FROM approved_moves WHERE book = ? AND id = ?", (book, move_id))
        else:
            con.execute("INSERT OR REPLACE INTO move_dates VALUES (?, ?, ?)", (book, move_id, book_date))
            if move is not None:
                con.execute("INSERT OR REPLACE INTO approved_moves VALUES (?, ?, ?)", (book, move_id, json.dumps(move, default=str)))


def approved_moves(db: Path, book: str) -> dict[str, dict]:
    with connect(db) as con:
        return {i: json.loads(d) for i, d in con.execute("SELECT id, data FROM approved_moves WHERE book = ?", (book,)).fetchall()}


def move_dates(db: Path, book: str) -> dict[str, str]:
    with connect(db) as con:
        return dict(con.execute("SELECT id, book_date FROM move_dates WHERE book = ?", (book,)).fetchall())


# ---------------------------------------------------------------- things the owner knows are coming (festive sales, a big order, a purchase)


def add_event(db: Path, book: str, date: str, amount: float, label: str) -> int:
    with connect(db) as con:
        cur = con.execute("INSERT INTO known_events (book, date, amount, label, created_at) VALUES (?,?,?,?,?)", (book, date, float(amount), label, store.now()))
        return int(cur.lastrowid)


def events(db: Path, book: str) -> list[dict]:
    with connect(db) as con:
        rows = con.execute("SELECT id, date, amount, label FROM known_events WHERE book = ? ORDER BY date", (book,)).fetchall()
    return [{"id": r[0], "date": r[1], "amount": r[2], "label": r[3]} for r in rows]


def delete_event(db: Path, book: str, event_id: int) -> None:
    with connect(db) as con:
        con.execute("DELETE FROM known_events WHERE book = ? AND id = ?", (book, event_id))


# ---------------------------------------------------------------- audit trail


def audit(db: Path, book: str) -> list[dict]:
    """Everything the agents did and everything the owner decided, oldest first."""
    out: list[dict] = []
    with connect(db) as con:
        for at, bd, agent, tone, text in con.execute("SELECT at, book_date, agent, tone, text FROM agent_activity WHERE book = ?", (book,)):
            out.append({"at": at, "book_date": bd, "who": f"agent:{agent}", "what": text, "kind": tone})
        dates = dict(con.execute("SELECT id, book_date FROM move_dates WHERE book = ?", (book,)).fetchall())
        for mid, state, at in con.execute("SELECT id, state, at FROM autopilot_moves WHERE book = ?", (book,)):
            out.append({"at": at, "book_date": dates.get(mid, ""), "who": "owner", "what": f"{state}: {mid}", "kind": "decision"})
        for at, kind, summary, undone in con.execute("SELECT at, kind, summary, undone FROM entry_log WHERE book = ?", (book,)):
            out.append({"at": at, "book_date": "", "who": "owner", "what": f"entry ({kind}): {summary}" + (" — undone" if undone else ""), "kind": "entry"})
        for at, kind, title, state, decided in con.execute("SELECT created_at, kind, title, state, decided_at FROM agent_actions WHERE book = ?", (book,)):
            out.append({"at": decided or at, "book_date": "", "who": "owner" if decided else "agent:assistant", "what": f"{kind} draft '{title}' — {state}", "kind": "draft"})
        for date, amount, label, at in con.execute("SELECT date, amount, label, created_at FROM known_events WHERE book = ?", (book,)):
            out.append({"at": at, "book_date": "", "who": "owner", "what": f"told FinPilot: {label} {amount:+,.0f} on {date}", "kind": "event"})
    out.sort(key=lambda r: r["at"] or "")
    return out
