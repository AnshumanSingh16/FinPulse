"""The active dataset: the fictional demo business, or the owner's own uploaded data (stored locally)."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd

from finpilot.data import store
from finpilot.data.demo import AS_OF as DEMO_AS_OF
from finpilot.data.demo import BUSINESS, load_demo


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


@lru_cache(maxsize=1)
def _demo_tables() -> dict:
    return load_demo()


def demo() -> Dataset:
    t = _demo_tables()
    return Dataset(BUSINESS, "demo", t["ledger"].copy(), t["obligations"].copy(), t["balances"].copy(), pd.Timestamp(DEMO_AS_OF))


def uploaded(db: Path) -> Dataset | None:
    saved = store.load_dataset(db)
    if not saved or saved.get("ledger") is None or not len(saved["ledger"]):
        return None
    return Dataset(saved["name"], "upload", saved["ledger"], saved.get("obligations"), saved.get("balances"), pd.Timestamp(saved["as_of"]))


def get_source(db: Path) -> str:
    with store.connect(db) as con:
        row = con.execute("SELECT value FROM meta WHERE key = 'source'").fetchone()
    return row[0] if row else "demo"


def set_source(db: Path, source: str) -> None:
    if source not in ("demo", "upload"):
        raise ValueError("source must be demo or upload")
    with store.connect(db) as con:
        con.execute("INSERT OR REPLACE INTO meta VALUES ('source', ?)", (source,))


def current(db: Path) -> Dataset:
    """The upload if the owner chose it and it exists; otherwise the demo."""
    if get_source(db) == "upload":
        ds = uploaded(db)
        if ds is not None:
            return ds
    return demo()


def raw_upload_tables(db: Path) -> dict:
    """Whatever has been uploaded so far (any table may be missing)."""
    saved = store.load_dataset(db) or {}
    return {t: saved.get(t) for t in store.TABLES} | {"name": saved.get("name") or "My business", "as_of": saved.get("as_of")}


def save_upload_table(db: Path, table: str, df: pd.DataFrame, name: str | None = None) -> Dataset | None:
    """Replace one table of the uploaded dataset, keep the others, and recompute the as-of date."""
    t = raw_upload_tables(db)
    t[table] = df
    as_of = t["as_of"]
    if t.get("ledger") is not None and len(t["ledger"]):
        as_of = str(pd.to_datetime(t["ledger"]["date"]).max().date())
    elif table == "balances" and len(df):
        as_of = str(pd.to_datetime(df["as_of"]).max().date())
    store.save_dataset(db, name or t["name"], {k: t[k] for k in store.TABLES}, as_of or str(pd.Timestamp.today().date()))
    return uploaded(db)


def set_as_of(db: Path, as_of: str) -> None:
    with store.connect(db) as con:
        con.execute("INSERT OR REPLACE INTO meta VALUES ('as_of', ?)", (str(pd.Timestamp(as_of).date()),))
