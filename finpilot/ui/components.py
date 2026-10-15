"""Reusable UI pieces: KPI cards, alerts, evidence panels, page headers."""

from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from finpilot.engine.common import fmt_inr


def header(eyebrow: str, title: str, sub: str | None = None) -> None:
    st.markdown(f'<div class="fp-eyebrow">{html.escape(eyebrow)}</div>', unsafe_allow_html=True)
    st.markdown(f"## {title}")
    if sub:
        st.markdown(f'<div class="fp-sub">{html.escape(sub)}</div>', unsafe_allow_html=True)


def kpi(label: str, value: str, note: str = "", tag: str | None = None, tag_kind: str = "") -> None:
    t = f' <span class="fp-tag {tag_kind}">{html.escape(tag)}</span>' if tag else ""
    st.markdown(
        f'<div class="fp-card"><div class="fp-kpi-label">{html.escape(label)}{t}</div>'
        f'<div class="fp-kpi-value">{html.escape(value)}</div>'
        f'<div class="fp-kpi-note">{html.escape(note)}</div></div>',
        unsafe_allow_html=True,
    )


def alert(kind: str, title: str, detail: str) -> None:
    st.markdown(
        f'<div class="fp-alert {kind}"><div class="bar"></div><div><div class="t">{html.escape(title)}</div>'
        f'<div class="d">{html.escape(detail)}</div></div></div>',
        unsafe_allow_html=True,
    )


def evidence_panel(evidence: dict, records: pd.DataFrame | None = None, title: str = "Evidence: how this was calculated", id_col: str = "txn_id", key: str = "") -> None:
    """Method, assumptions, limitations and the supporting records behind a result."""
    with st.expander(title, expanded=False):
        st.markdown(f"**Method.** {evidence.get('method', '')}")
        if evidence.get("period"):
            p = evidence["period"]
            st.markdown(f"**Period.** {p[0]} to {p[1]}")
        if evidence.get("assumptions"):
            st.markdown("**Assumptions**")
            for a in evidence["assumptions"]:
                st.markdown(f"- {a}")
        if evidence.get("limitations"):
            st.markdown("**Limitations**")
            for lim in evidence["limitations"]:
                st.markdown(f"- {lim}")
        ids = evidence.get("record_ids") or []
        if records is not None and ids:
            sub = records[records[id_col].isin(ids)]
            st.markdown(f"**Supporting records** ({len(sub)})")
            show = sub.copy()
            for c in show.columns:
                if pd.api.types.is_datetime64_any_dtype(show[c]):
                    show[c] = show[c].dt.date
            st.dataframe(show, hide_index=True, use_container_width=True, height=min(320, 38 + 35 * len(show)), key=f"ev_{key}_{len(ids)}")
        elif ids:
            st.markdown(f"**Supporting record ids** ({len(ids)}): " + ", ".join(ids[:40]) + (" …" if len(ids) > 40 else ""))


def inr(x: float | None) -> str:
    return "—" if x is None else fmt_inr(x)
