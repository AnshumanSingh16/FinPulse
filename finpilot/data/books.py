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


DEFAULT_SETTINGS = {"gst_registered": "yes", "gst_rate_sales": "5", "gst_rate_purchases": "5", "gst_filing": "monthly", "language": "en"}


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
        for t in ("contacts", "promises", "cat_rules", "budgets", "goals", "settings", "entry_log"):
            con.execute(f"DELETE FROM {t} WHERE book = ?", (book,))
