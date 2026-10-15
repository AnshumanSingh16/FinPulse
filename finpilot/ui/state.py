"""The active dataset, kept in Streamlit session state."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd
import streamlit as st

from finpilot.config import settings
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
    reports: dict = field(default_factory=dict)

    @property
    def is_demo(self) -> bool:
        return self.source == "demo"


@st.cache_data(show_spinner=False)
def _demo_tables():
    return load_demo()


def demo_dataset() -> Dataset:
    t = _demo_tables()
    return Dataset(
        name=BUSINESS,
        source="demo",
        ledger=t["ledger"].copy(),
        obligations=t["obligations"].copy(),
        balances=t["balances"].copy(),
        as_of=pd.Timestamp(DEMO_AS_OF),
    )


def uploaded_dataset() -> Dataset | None:
    saved = store.load_dataset(settings().db_path)
    if not saved or saved.get("ledger") is None:
        return None
    return Dataset(
        name=saved["name"],
        source="upload",
        ledger=saved["ledger"],
        obligations=saved.get("obligations"),
        balances=saved.get("balances"),
        as_of=pd.Timestamp(saved["as_of"]),
    )


def current() -> Dataset:
    """The dataset the pages work on: the upload if chosen and present, else the demo."""
    mode = st.session_state.get("data_source", "demo")
    if mode == "upload":
        ds = uploaded_dataset()
        if ds is not None:
            if "as_of_override" in st.session_state:
                ds.as_of = pd.Timestamp(st.session_state["as_of_override"])
            return ds
        st.session_state["data_source"] = "demo"
    return demo_dataset()
