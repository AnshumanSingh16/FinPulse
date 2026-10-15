"""
The active book: the fictional demo shop or the owner's own data. Both are editable — quick entries,
payments and corrections are saved to local SQLite. The demo starts from the fixed CSV dataset and
can be reset at any time.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd

from finpilot.data import books, khata, store
from finpilot.data.demo import AS_OF as DEMO_AS_OF
from finpilot.data.demo import BUSINESS, load_demo

BOOKS = ("demo", "upload")


@dataclass
class Dataset:
    name: str
    source: str  # "demo" | "upload"
    ledger: pd.DataFrame
    obligations: pd.DataFrame | None
    balances: pd.DataFrame | None
    as_of: pd.Timestamp

    @property
    def is_demo(self) -> bool:
        return self.source == "demo"

    @property
    def book(self) -> str:
        return self.source

    def tables(self) -> khata.Tables:
        return khata.Tables(self.ledger, self.obligations, self.balances)


def today() -> pd.Timestamp:
    """The real date (patched in tests)."""
    return pd.Timestamp.today().normalize()


@lru_cache(maxsize=1)
def _demo_tables() -> dict:
    return load_demo()


def _pinned_as_of(db: Path) -> str | None:
    with store.connect(db) as con:
        row = con.execute("SELECT value FROM meta WHERE key = 'upload:as_of_pinned'").fetchone()
    return row[0] if row else None


def load(db: Path, book: str) -> Dataset | None:
    if book == "demo":
        saved = store.load_dataset(db, "demo")
        if saved is None:
            t = _demo_tables()
            return Dataset(BUSINESS, "demo", t["ledger"].copy(), t["obligations"].copy(), t["balances"].copy(), pd.Timestamp(DEMO_AS_OF))
        return Dataset(saved["name"], "demo", saved["ledger"], saved.get("obligations"), saved.get("balances"), pd.Timestamp(DEMO_AS_OF))
    return load_started(db)


def demo() -> Dataset:
    return load(Path(":memory:"), "demo")  # type: ignore[return-value]


def uploaded(db: Path) -> Dataset | None:
    return load(db, "upload")


def save(db: Path, ds: Dataset, tables: khata.Tables) -> Dataset:
    """Write the book's tables back (the demo is copied on its first change)."""
    store.save_dataset(db, ds.name, {"ledger": tables.ledger, "obligations": tables.obligations, "balances": tables.balances}, str(ds.as_of.date()), book=ds.book)
    return load(db, ds.book)  # type: ignore[return-value]


def reset_demo(db: Path) -> None:
    store.clear_dataset(db, "demo")
    books.reset_book(db, "demo")


def get_source(db: Path) -> str:
    with store.connect(db) as con:
        row = con.execute("SELECT value FROM meta WHERE key = 'source'").fetchone()
    return row[0] if row else "demo"


def set_source(db: Path, source: str) -> None:
    if source not in BOOKS:
        raise ValueError("source must be demo or upload")
    with store.connect(db) as con:
        con.execute("INSERT OR REPLACE INTO meta VALUES ('source', ?)", (source,))


def current(db: Path) -> Dataset:
    """The upload if the owner chose it and it exists; otherwise the demo."""
    if get_source(db) == "upload":
        ds = uploaded(db)
        if ds is not None:
            return ds
    return load(db, "demo")  # type: ignore[return-value]


def raw_upload_tables(db: Path) -> dict:
    """Whatever has been uploaded so far (any table may be missing)."""
    saved = store.load_dataset(db, "upload") or {}
    return {t: saved.get(t) for t in store.TABLES} | {"name": saved.get("name") or "My business", "as_of": saved.get("as_of")}


def save_upload_table(db: Path, table: str, df: pd.DataFrame, name: str | None = None) -> Dataset | None:
    """Replace one table of the uploaded book and keep the others."""
    t = raw_upload_tables(db)
    t[table] = df
    as_of = t["as_of"] or str(today().date())
    if t.get("ledger") is not None and len(t["ledger"]):
        as_of = str(pd.to_datetime(t["ledger"]["date"]).max().date())
    store.save_dataset(db, name or t["name"], {k: t[k] for k in store.TABLES}, as_of, book="upload")
    return uploaded(db)


def set_as_of(db: Path, as_of: str | None) -> None:
    with store.connect(db) as con:
        if as_of:
            con.execute("INSERT OR REPLACE INTO meta VALUES ('upload:as_of_pinned', ?)", (str(pd.Timestamp(as_of).date()),))
        else:
            con.execute("DELETE FROM meta WHERE key = 'upload:as_of_pinned'")


def start_fresh(db: Path, name: str, opening_balance: float | None, on: str | None) -> Dataset:
    """Start an empty book for an owner with no files: just a name and (optionally) today's balance."""
    when = pd.Timestamp(on or today()).normalize()
    bal = khata.empty_balances()
    if opening_balance is not None:
        bal = pd.DataFrame([{"as_of": when, "account": "Main account", "balance": float(opening_balance)}])
    store.save_dataset(db, name or "My business", {"ledger": khata.empty_ledger(), "obligations": None, "balances": bal}, str(when.date()), book="upload")
    with store.connect(db) as con:
        con.execute("INSERT OR REPLACE INTO meta VALUES ('upload:started', '1')")
    set_source(db, "upload")
    return load_started(db)  # type: ignore[return-value]


def load_started(db: Path) -> Dataset | None:
    """An uploaded book that may still have no transactions (started fresh)."""
    saved = store.load_dataset(db, "upload")
    if not saved:
        return None
    led = saved["ledger"] if saved.get("ledger") is not None else khata.empty_ledger()
    if "txn_id" not in led:
        led = khata.empty_ledger()
    led["date"] = pd.to_datetime(led["date"])
    pinned = _pinned_as_of(db)
    last = pd.to_datetime(led["date"]).max() if len(led) else today()
    as_of = pd.Timestamp(pinned) if pinned else max(today(), last.normalize())
    return Dataset(saved["name"], "upload", led, saved.get("obligations"), saved.get("balances"), as_of)
