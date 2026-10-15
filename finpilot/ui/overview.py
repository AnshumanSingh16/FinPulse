"""Overview: KPIs, charts and alerts for the active dataset."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from finpilot.engine.alerts import build_alerts
from finpilot.engine.cash import cash_position, obligations_status
from finpilot.engine.common import prepare_ledger
from finpilot.engine.summary import financial_summary
from finpilot.ui import components as c
from finpilot.ui import state
from finpilot.ui.theme import INFLOW, OUTFLOW, lakh_axis, plotly_layout


def _period_choice(ds: state.Dataset):
    first = pd.Timestamp(ds.ledger["date"].min())
    options = {
        "Last 3 months": ds.as_of - pd.DateOffset(months=3) + pd.Timedelta(days=1),
        "Last 6 months": ds.as_of - pd.DateOffset(months=6) + pd.Timedelta(days=1),
        "Last 12 months": ds.as_of - pd.DateOffset(months=12) + pd.Timedelta(days=1),
        "All data": first,
    }
    label = st.segmented_control("Period", list(options), default="Last 12 months", key="ov_period", label_visibility="collapsed")
    label = label or "Last 12 months"
    return label, max(options[label], first), ds.as_of


def render() -> None:
    ds = state.current()
    c.header(
        "Overview",
        ds.name,
        f"Figures to {ds.as_of.date():%d %b %Y} · {'Demo data — fictional business' if ds.is_demo else 'Your uploaded data'}",
    )
    label, start, end = _period_choice(ds)
    s = financial_summary(ds.ledger, start, end, ds.obligations, ds.as_of)
    if s["status"] != "ok":
        st.warning(s["message"])
        return
    pos = cash_position(ds.ledger, ds.balances, ds.as_of)
    obl = obligations_status(ds.obligations, ds.as_of)

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        c.kpi("Revenue", c.inr(s["revenue"]), f"Sales received · {label.lower()}", "cash basis")
    with k2:
        c.kpi("Recorded expenses", c.inr(s["operating_expenses"]), "Operating costs paid", "recorded")
    with k3:
        m = f"{s['estimated_margin_pct']:.1f}% margin" if s["estimated_margin_pct"] is not None else ""
        c.kpi("Estimated operating profit", c.inr(s["estimated_operating_profit"]), f"{m} · before depreciation & accruals", "estimate", "est")
    with k4:
        if pos["status"] == "ok":
            rec = pos["reconciliation"]
            tag = "reconciled" if rec and all(x["reconciled"] for x in rec) else "from balance"
            c.kpi("Cash in bank", c.inr(pos["cash_balance"]), f"Balance of {pos['anchor_balance']['as_of']} + later movements", tag, "verified" if tag == "reconciled" else "")
        else:
            c.kpi("Cash in bank", "Unknown", "Add a dated bank balance", "missing", "est")

    k5, k6, k7, k8 = st.columns(4)
    with k5:
        c.kpi("Net cash movement", c.inr(s["net_cash_movement"]), "All money in − all money out")
    if obl["status"] == "ok":
        with k6:
            r = obl["receivables"]
            c.kpi("Customers owe you", c.inr(r["pending_not_due"] + r["overdue"]), f"{c.inr(r['overdue'])} overdue")
        with k7:
            p = obl["payables"]
            c.kpi("You owe suppliers", c.inr(p["pending_not_due"] + p["overdue"]), f"{c.inr(p['overdue'])} overdue")
    with k8:
        o = s["other_flows"]
        c.kpi("Outside operating profit", c.inr(o["capex"] + o["loan_repayments"] + o["owner_drawings"] + o["tax_remitted"]), "Assets, loan EMIs, drawings, GST paid")

    st.write("")
    left, right = st.columns([3, 2], gap="medium")
    with left:
        st.markdown("#### Revenue and recorded expenses by month")
        mdf = pd.DataFrame(s["monthly"])
        fig = go.Figure()
        fig.add_bar(name="Revenue", x=mdf["month"], y=mdf["revenue"], marker_color=INFLOW, hovertemplate="%{x}<br>Revenue ₹%{y:,.0f}<extra></extra>")
        fig.add_bar(name="Recorded expenses", x=mdf["month"], y=mdf["operating_expenses"], marker_color=OUTFLOW, hovertemplate="%{x}<br>Expenses ₹%{y:,.0f}<extra></extra>")
        fig.update_layout(barmode="group", bargap=0.25, bargroupgap=0.08)
        lakh_axis(fig, list(mdf["revenue"]) + list(mdf["operating_expenses"]))
        st.plotly_chart(plotly_layout(fig, 300), use_container_width=True, config={"displayModeBar": False})
        with st.expander("Monthly table"):
            st.dataframe(mdf.rename(columns={"month": "Month", "revenue": "Revenue", "operating_expenses": "Recorded expenses", "estimated_operating_profit": "Est. operating profit", "net_cash_movement": "Net cash movement"}), hide_index=True, use_container_width=True)
    with right:
        st.markdown("#### Where the money went")
        cats = pd.Series(s["expenses_by_category"]).sort_values()
        fig2 = go.Figure(go.Bar(x=cats.values, y=cats.index, orientation="h", marker_color=OUTFLOW, hovertemplate="%{y}<br>₹%{x:,.0f}<extra></extra>"))
        lakh_axis(fig2, list(cats.values), axis="x")
        st.plotly_chart(plotly_layout(fig2, 300), use_container_width=True, config={"displayModeBar": False})

    left, right = st.columns([3, 2], gap="medium")
    with left:
        st.markdown("#### Bank balance")
        if pos["status"] == "ok":
            df = prepare_ledger(ds.ledger)
            bal = ds.balances.sort_values("as_of")
            anchor = bal.iloc[0]
            rows = df[df["date"] > anchor["as_of"]].groupby("date")["signed"].sum().cumsum() + anchor["balance"]
            series = pd.concat([pd.Series({anchor["as_of"]: anchor["balance"]}), rows])
            series = series[(series.index >= start - pd.Timedelta(days=1)) & (series.index <= end)]
            fig3 = go.Figure(go.Scatter(x=series.index, y=series.values, mode="lines", line=dict(color=INFLOW, width=2, shape="hv"), name="Balance from ledger", hovertemplate="%{x|%d %b %Y}<br>₹%{y:,.0f}<extra></extra>"))
            stated = bal[(bal["as_of"] >= start - pd.Timedelta(days=1)) & (bal["as_of"] <= end)]
            fig3.add_scatter(x=stated["as_of"], y=stated["balance"], mode="markers", marker=dict(size=10, color="#111827", symbol="diamond", line=dict(color="white", width=2)), name="Statement balance", hovertemplate="Statement %{x|%d %b %Y}<br>₹%{y:,.0f}<extra></extra>")
            lakh_axis(fig3, list(series.values) + list(stated["balance"]))
            st.plotly_chart(plotly_layout(fig3, 280), use_container_width=True, config={"displayModeBar": False})
        else:
            st.info(pos["message"])
    with right:
        st.markdown("#### Alerts")
        alerts = build_alerts(ds.ledger, ds.balances, ds.obligations, ds.as_of)
        if not alerts:
            st.success("Nothing needs attention.")
        for a in alerts:
            c.alert(a["kind"], a["title"], a["detail"])

    c.evidence_panel(s["evidence"], ds.ledger, title="Evidence: how these figures were calculated", key="ov")
    if pos["status"] == "ok":
        c.evidence_panel(pos["evidence"], None, title="Evidence: cash in bank", key="ov_cash")
