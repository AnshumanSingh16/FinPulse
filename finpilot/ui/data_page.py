"""Upload, map, validate and save the user's data (kept locally in SQLite)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from finpilot.config import settings
from finpilot.data import store
from finpilot.data.demo import DEMO_DIR
from finpilot.data.loader import (
    TABLE_FIELDS,
    build_balances,
    build_ledger,
    build_obligations,
    excel_sheets,
    read_table,
    suggest_mapping,
)
from finpilot.ui import components as c

FIELD_HELP = {
    "ledger": "One row per money movement (bank statement or cash book). Required: date and an amount (one signed column, amount + Dr/Cr column, or separate debit/credit columns).",
    "obligations": "Invoices you've sent (receivables) and bills you've received (payables), with due dates and paid/pending status.",
    "balances": "At least one bank balance with its date — the starting point for cash. Without it, cash can't be known.",
}
REQUIRED = {"ledger": ["date"], "obligations": ["kind", "amount", "due_date", "status"], "balances": ["as_of", "balance"]}
BUILDERS = {"ledger": build_ledger, "obligations": build_obligations, "balances": build_balances}


def _mapping_ui(table: str, raw: pd.DataFrame) -> dict:
    suggested = suggest_mapping(list(raw.columns), table)
    opts = ["— not in file —"] + list(raw.columns)
    cols = st.columns(4)
    mapping = {}
    for i, f in enumerate(TABLE_FIELDS[table]):
        default = suggested.get(f)
        with cols[i % 4]:
            choice = st.selectbox(
                f + (" *" if f in REQUIRED[table] else ""),
                opts,
                index=opts.index(default) if default in opts else 0,
                key=f"map_{table}_{f}",
            )
        mapping[f] = None if choice == opts[0] else choice
    return mapping


def _report(rep) -> None:
    ok = rep.rows_ok
    st.markdown(f"**{ok} of {rep.rows_in} rows accepted.**")
    for w in rep.warnings:
        c.alert("caution", "Check", w)
    if rep.rejected:
        with st.expander(f"{len(rep.rejected)} row(s) not imported — reasons"):
            st.dataframe(pd.DataFrame(rep.rejected), hide_index=True, use_container_width=True)
    if rep.filled:
        st.caption("Filled-in values: " + ", ".join(f"{k}: {v}" for k, v in rep.filled.items()))


def _upload_block(table: str, label: str) -> pd.DataFrame | None:
    st.markdown(f"#### {label}")
    st.caption(FIELD_HELP[table])
    up = st.file_uploader(f"{label} (.csv or .xlsx)", type=["csv", "xlsx"], key=f"up_{table}", label_visibility="collapsed")
    if up is None:
        return None
    data = up.getvalue()
    sheet = 0
    if up.name.lower().endswith(".xlsx"):
        sheets = excel_sheets(data)
        if len(sheets) > 1:
            sheet = st.selectbox("Sheet", sheets, key=f"sheet_{table}")
    try:
        raw = read_table(data, up.name, sheet)
    except Exception as e:  # noqa: BLE001 — show the reason, don't crash the page
        st.error(f"Couldn't read the file: {e}")
        return None
    st.caption(f"{len(raw)} rows · columns: {', '.join(map(str, raw.columns))}")
    with st.expander("Preview", expanded=False):
        st.dataframe(raw.head(8), hide_index=True, use_container_width=True)
    mapping = _mapping_ui(table, raw)
    kwargs = {}
    if table == "ledger":
        kwargs["drop_exact_duplicates"] = st.checkbox(
            "Drop exact duplicate rows (identical in every field)", value=False, key="drop_dups",
            help="Off by default: two identical payments can be genuine. Possible duplicates are always reported.",
        )
    df, rep = BUILDERS[table](raw, mapping, **kwargs)
    _report(rep)
    return df if rep.ok else None


def render() -> None:
    cfg = settings()
    c.header("Your data", "Data & uploads", "Upload your records. They are parsed and stored only on this computer (SQLite file); nothing is sent anywhere by uploading.")

    with st.expander("Don't have files ready? Download the demo files to see the expected shape"):
        cols = st.columns(3)
        for col, name in zip(cols, ("ledger", "obligations", "balances")):
            with col:
                st.download_button(f"{name}.csv", (DEMO_DIR / f"{name}.csv").read_bytes(), file_name=f"demo_{name}.csv", mime="text/csv", key=f"dl_{name}")

    business = st.text_input("Business name", value="My business", key="biz_name")
    ledger = _upload_block("ledger", "1. Transactions (required)")
    obligations = _upload_block("obligations", "2. Invoices and bills (optional)")
    balances = _upload_block("balances", "3. Bank balance (needed for cash)")
    if balances is None:
        with st.container(border=True):
            st.caption("…or type one dated balance:")
            b1, b2 = st.columns(2)
            with b1:
                bdate = st.date_input("Balance date", value=None, key="man_bal_date")
            with b2:
                bamt = st.number_input("Balance (₹)", value=None, step=1000.0, key="man_bal_amt")
            if bdate and bamt is not None:
                balances = pd.DataFrame({"as_of": [pd.Timestamp(bdate)], "account": ["Main account"], "balance": [float(bamt)]})

    st.divider()
    if ledger is None:
        st.info("Upload a transactions file to continue. Until then the app uses the demo business.")
    else:
        default_as_of = pd.Timestamp(ledger["date"].max()).date()
        as_of = st.date_input("Figures as of", value=default_as_of, key="up_as_of", help="Usually the last date your records cover.")
        if balances is None:
            c.alert("caution", "No bank balance", "Revenue and expenses will work, but cash position, forecasts and purchase simulations need a dated balance.")
        if st.button("Save and use this data", type="primary"):
            store.save_dataset(cfg.db_path, business, {"ledger": ledger, "obligations": obligations, "balances": balances}, str(as_of))
            st.session_state["data_source"] = "upload"
            st.session_state.pop("as_of_override", None)
            st.success("Saved. Switched to your data.")
            st.rerun()

    if store.load_dataset(cfg.db_path):
        st.divider()
        if st.button("Delete my uploaded data from this computer"):
            store.clear_dataset(cfg.db_path)
            st.session_state["data_source"] = "demo"
            st.rerun()

    with st.expander("Approval queue and activity log"):
        st.caption("FinPilot can only propose actions. Nothing is executed — approving simply records your decision.")
        items = store.approvals(cfg.db_path)
        if not items:
            st.caption("No proposed actions.")
        for it in items:
            cols = st.columns([5, 1, 1])
            cols[0].markdown(f"**{it['action']}** · {it['status']} · {it['created_at']}  \n{it['details']}")
            if it["status"] == "pending":
                if cols[1].button("Approve", key=f"ap_{it['id']}"):
                    store.decide_action(cfg.db_path, it["id"], "approved")
                    st.rerun()
                if cols[2].button("Reject", key=f"rj_{it['id']}"):
                    store.decide_action(cfg.db_path, it["id"], "rejected")
                    st.rerun()
        log = store.activity(cfg.db_path, 30)
        if log:
            st.dataframe(pd.DataFrame(log), hide_index=True, use_container_width=True)
