"""
Local SQLite storage: the uploaded dataset (so a refresh doesn't lose it), an activity log, and an
approval queue for proposed actions. The database is a local file; nothing here leaves the machine.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

TABLES = ("ledger", "obligations", "balances")
DATE_COLS = {"ledger": ["date"], "obligations": ["issue_date", "due_date", "paid_date"], "balances": ["as_of"]}


@contextmanager
def connect(path: Path):
    con = sqlite3.connect(path)
    try:
        con.execute(
            "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)"
        )
        con.execute(
            "CREATE TABLE IF NOT EXISTS activity (id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, kind TEXT, detail TEXT)"
        )
        con.execute(
            "CREATE TABLE IF NOT EXISTS approvals (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, "
            "action TEXT, details TEXT, status TEXT, decided_at TEXT)"
        )
        yield con
        con.commit()
    finally:
        con.close()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _meta_key(book: str, key: str) -> str:
    # The uploaded book keeps its original key names so existing databases still load.
    return key if book == "upload" else f"{book}:{key}"


def save_dataset(path: Path, name: str, tables: dict[str, pd.DataFrame], as_of: str, book: str = "upload") -> None:
    with connect(path) as con:
        for t in TABLES:
            df = tables.get(t)
            if df is None:
                con.execute(f"DROP TABLE IF EXISTS {book}_{t}")
                continue
            out = df.copy()
            for c in DATE_COLS[t]:
                if c in out:
                    out[c] = pd.to_datetime(out[c]).dt.strftime("%Y-%m-%d")
            out.to_sql(f"{book}_{t}", con, if_exists="replace", index=False)
        con.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (_meta_key(book, "dataset_name"), name))
        con.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (_meta_key(book, "as_of"), as_of))
        if book == "upload":
            con.execute("INSERT INTO activity (at, kind, detail) VALUES (?, ?, ?)", (now(), "dataset_saved", name))


def load_dataset(path: Path, book: str = "upload") -> dict | None:
    if not Path(path).exists():
        return None
    with connect(path) as con:
        meta = dict(con.execute("SELECT key, value FROM meta").fetchall())
        if _meta_key(book, "dataset_name") not in meta:
            return None
        out: dict = {"name": meta[_meta_key(book, "dataset_name")], "as_of": meta.get(_meta_key(book, "as_of"))}
        names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for t in TABLES:
            if f"{book}_{t}" not in names:
                out[t] = None
                continue
            df = pd.read_sql(f"SELECT * FROM {book}_{t}", con)
            for c in DATE_COLS[t]:
                if c in df:
                    df[c] = pd.to_datetime(df[c])
            out[t] = df
        return out


def clear_dataset(path: Path, book: str = "upload") -> None:
    with connect(path) as con:
        for t in TABLES:
            con.execute(f"DROP TABLE IF EXISTS {book}_{t}")
        con.execute("DELETE FROM meta WHERE key IN (?, ?)", (_meta_key(book, "dataset_name"), _meta_key(book, "as_of")))
        con.execute("INSERT INTO activity (at, kind, detail) VALUES (?, ?, ?)", (now(), "dataset_cleared", book))


def log(path: Path, kind: str, detail: str) -> None:
    with connect(path) as con:
        con.execute("INSERT INTO activity (at, kind, detail) VALUES (?, ?, ?)", (now(), kind, detail[:2000]))


def activity(path: Path, limit: int = 50) -> list[dict]:
    with connect(path) as con:
        rows = con.execute("SELECT at, kind, detail FROM activity ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [{"at": a, "kind": k, "detail": d} for a, k, d in rows]


# ---------------------------------------------------------------- approvals
# FinPilot never acts outside the app. The assistant can only *propose* an action; a person decides,
# and even an approved item is just recorded — the MVP has no integration that executes anything.


def propose_action(path: Path, action: str, details: dict) -> int:
    with connect(path) as con:
        cur = con.execute(
            "INSERT INTO approvals (created_at, action, details, status, decided_at) VALUES (?, ?, ?, 'pending', NULL)",
            (now(), action, json.dumps(details, default=str)),
        )
        con.execute("INSERT INTO activity (at, kind, detail) VALUES (?, ?, ?)", (now(), "action_proposed", action))
        return int(cur.lastrowid)


def decide_action(path: Path, approval_id: int, decision: str) -> None:
    if decision not in ("approved", "rejected"):
        raise ValueError("decision must be approved or rejected")
    with connect(path) as con:
        row = con.execute("SELECT status FROM approvals WHERE id = ?", (approval_id,)).fetchone()
        if row is None:
            raise KeyError(approval_id)
        if row[0] != "pending":
            raise ValueError(f"already {row[0]}")
        con.execute("UPDATE approvals SET status = ?, decided_at = ? WHERE id = ?", (decision, now(), approval_id))
        con.execute("INSERT INTO activity (at, kind, detail) VALUES (?, ?, ?)", (now(), f"action_{decision}", str(approval_id)))


def approvals(path: Path) -> list[dict]:
    with connect(path) as con:
        rows = con.execute("SELECT id, created_at, action, details, status, decided_at FROM approvals ORDER BY id DESC").fetchall()
    return [
        {"id": i, "created_at": c, "action": a, "details": json.loads(d), "status": s, "decided_at": t}
        for i, c, a, d, s, t in rows
    ]
