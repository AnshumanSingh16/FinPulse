"""Decision Lab: purchase simulations and cash-flow scenarios, run directly on the tested engine."""

from __future__ import annotations

import html

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from finpilot.engine.decision import Purchase, default_buffer, simulate_purchase
from finpilot.engine.forecast import ForecastOptions, forecast_cash_flow
from finpilot.ui import components as c
from finpilot.ui import state
from finpilot.ui.theme import BAD, CAUTION, GOOD, INFLOW, OUTFLOW, lakh_axis, plotly_layout

SCEN_COLOR = {"optimistic": GOOD, "base": INFLOW, "downside": OUTFLOW}


def _cash_unknown(ds: state.Dataset) -> bool:
    if ds.balances is None or not len(ds.balances) or pd.Timestamp(ds.balances["as_of"].min()) > ds.as_of:
        st.warning(
            "**Cash position unknown.** Simulations start from the actual bank balance, and there is no dated balance on or before "
            f"{ds.as_of.date()}. Add one on the Data & uploads page — FinPilot will not estimate cash from revenue minus expenses.",
            icon=":material/account_balance:",
        )
        return True
    return False


# ---------------------------------------------------------------- purchase


def _purchase_form(ds: state.Dataset) -> tuple[Purchase | None, dict]:
    with st.container(border=True):
        st.markdown("##### What are you buying?")
        name = st.text_input("Item", "Automatic packing machine", key="dl_name")
        a, b = st.columns(2)
        cost = a.number_input("Price (₹)", min_value=1_000.0, value=12_00_000.0, step=10_000.0, format="%.0f", key="dl_cost")
        when = b.date_input("Purchase date", value=ds.as_of.date(), min_value=ds.as_of.date(), key="dl_date")
        financing = st.segmented_control("Paid with", ["cash", "loan"], default="loan", format_func=str.title, key="dl_fin") or "cash"
        rate = tenure = None
        down = 100.0
        if financing == "loan":
            a, b, cc = st.columns(3)
            down = a.number_input("Down pay %", 0.0, 99.0, 20.0, 5.0, key="dl_down")
            rate = b.number_input("Interest %/yr", 0.0, 40.0, value=None, step=0.25, placeholder="lender's rate", key="dl_rate")
            yrs = cc.number_input("Months", 1, 360, value=None, step=6, placeholder="tenure", key="dl_ten")
            tenure = int(yrs) if yrs else None

        st.markdown("##### What will it change?")
        a, b = st.columns(2)
        benefit = a.number_input("Extra cash per month (₹)", 0.0, value=45_000.0, step=5_000.0, format="%.0f", help="Savings or extra sales you expect. Your estimate — FinPilot cannot verify it.", key="dl_ben")
        start = b.number_input("Benefit starts after (months)", 0, 36, 1, key="dl_bstart")
        a, b = st.columns(2)
        running = a.number_input("Running cost per month (₹)", 0.0, value=4_000.0, step=1_000.0, format="%.0f", help="Maintenance, power, operator…", key="dl_run")
        one_time = b.number_input("One-time costs (₹)", 0.0, value=35_000.0, step=5_000.0, format="%.0f", help="Installation, training, transport.", key="dl_once")

        st.markdown("##### Safety settings")
        auto = default_buffer(ds.ledger, ds.as_of)
        a, b = st.columns(2)
        buffer = a.number_input("Keep at least (₹) in the bank", 0.0, value=float(round(auto, -3)), step=25_000.0, format="%.0f", help=f"Default: one month of typical operating costs ({c.inr(auto)}).", key="dl_buf")
        horizon = b.select_slider("Look ahead", [90, 180, 270, 365], 180, format_func=lambda d: f"{d} days", key="dl_hor")

    missing = []
    if financing == "loan":
        if rate is None:
            missing.append("interest rate")
        if tenure is None:
            missing.append("tenure")
    if missing:
        st.info(f"Enter the loan's {' and '.join(missing)} from your lender's quote. FinPilot does not assume loan terms.", icon=":material/edit_note:")
        return None, {}
    p = Purchase(
        name=name or "Purchase", cost=float(cost), purchase_date=str(when), financing=financing,
        down_payment_pct=float(down), loan_rate_pct=float(rate or 0), tenure_months=int(tenure or 12),
        monthly_benefit=float(benefit), benefit_start_months=int(start), monthly_running_cost=float(running), one_time_costs=float(one_time),
    )
    return p, {"min_buffer": float(buffer), "horizon_days": int(horizon)}


def _scenario_chart(r: dict, buffer: float) -> go.Figure:
    fig = go.Figure()
    vals = []
    base = next(s for s in r["scenarios"] if s["scenario"] == "base")
    wo = pd.DataFrame(base["daily_without"])
    vals += list(wo["balance"])
    fig.add_scatter(x=wo["date"], y=wo["balance"], mode="lines", line=dict(color="#94a3b8", width=1.6, dash="dot"),
                    name="Base · no purchase", hovertemplate="%{x|%d %b %Y}<br>₹%{y:,.0f}<extra>Base, no purchase</extra>")
    for key in ("optimistic", "base", "downside"):
        s = next(x for x in r["scenarios"] if x["scenario"] == key)
        w = pd.DataFrame(s["daily_with"])
        vals += list(w["balance"])
        fig.add_scatter(x=w["date"], y=w["balance"], mode="lines", line=dict(color=SCEN_COLOR[key], width=2.4 if key == "base" else 1.8),
                        name=f"{s['label']} · with purchase", hovertemplate="%{x|%d %b %Y}<br>₹%{y:,.0f}<extra>" + s["label"] + "</extra>")
    fig.add_hline(y=buffer, line=dict(color=CAUTION, width=1.2, dash="dash"), annotation_text=f"Buffer {c.inr(buffer)}",
                  annotation_position="bottom right", annotation_font_color=CAUTION)
    if min(vals) < 0:
        fig.add_hline(y=0, line=dict(color=BAD, width=1))
    lakh_axis(fig, vals + [buffer, 0])
    plotly_layout(fig, 360)
    fig.update_layout(margin=dict(l=8, r=8, t=36, b=8))
    return fig


def _purchase_tab(ds: state.Dataset) -> None:
    left, right = st.columns([2, 3], gap="large")
    with left:
        p, opts = _purchase_form(ds)
    with right:
        if p is None:
            return
        r = simulate_purchase(ds.ledger, ds.balances, ds.obligations, ds.as_of, p, horizon_days=opts["horizon_days"], min_buffer=opts["min_buffer"])
        if r["status"] != "ok":
            st.warning(r.get("message", "The simulation could not run."))
            return
        tone = r["verdict_tone"]
        icon = {"good": "✓", "caution": "⚠", "bad": "✗"}[tone]
        st.markdown(
            f'<div class="fp-verdict {tone}"><div class="fp-kpi-label">Verdict · {html.escape(p.name)}</div>'
            f'<div style="font-size:1.15rem;font-weight:650;margin-top:.2rem">{icon} {html.escape(r["verdict"])}</div>'
            f'<div class="fp-kpi-note">Judged on the downside scenario against a {html.escape(c.inr(r["buffer"]))} buffer, over {r["horizon_days"]} days.</div></div>',
            unsafe_allow_html=True,
        )
        st.write("")
        sc = {s["scenario"]: s for s in r["scenarios"]}
        k1, k2 = st.columns(2)
        with k1:
            c.kpi("Upfront cash", c.inr(r["upfront_cash"]), "Down payment + one-time costs" if p.financing == "loan" else "Price + one-time costs")
        with k2:
            c.kpi("EMI", c.inr(r["emi"]) if r["emi"] else "—", f"{p.tenure_months} months at {p.loan_rate_pct:g}%" if p.financing == "loan" else "Paid in cash")
        k3, k4 = st.columns(2)
        with k3:
            d = sc["downside"]["with_purchase"]
            c.kpi("Downside low point", c.inr(d["lowest_balance"]), f"on {d['lowest_balance_date']}", "downside", "est")
        with k4:
            c.kpi("Simple payback", f"{r['payback_months']:.0f} months" if r["payback_months"] else "—", "From your benefit estimate", "estimate", "est")
        st.plotly_chart(_scenario_chart(r, r["buffer"]), use_container_width=True, config={"displayModeBar": False})

        rows = []
        for key in ("downside", "base", "optimistic"):
            sc_ = sc[key]
            w, wo = sc_["with_purchase"], sc_["without_purchase"]
            rows.append({
                "Scenario": sc_["label"],
                "Lowest (with)": c.inr(w["lowest_balance"]),
                "On": w["lowest_balance_date"],
                "Lowest (without)": c.inr(wo["lowest_balance"]),
                "Net cash of purchase": c.inr(sc_["purchase_cash_impact"]),
                "Below buffer": w["first_date_below_buffer"] or "never",
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        with st.expander("What each scenario assumes"):
            for s in r["scenarios"]:
                st.markdown(f"**{s['label']}** — " + ", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in s["settings"].items()))
        if r.get("total_loan_interest"):
            st.caption(f"Total interest over the loan: {c.inr(r['total_loan_interest'])}. Costs inside EMIs are cash outflows; only the interest part is an expense for profit.")
        c.evidence_panel(r["evidence"], ds.obligations, title="Evidence: how this simulation works", id_col="item_id", key="dl_p")


# ---------------------------------------------------------------- cash-flow explorer


def _cash_tab(ds: state.Dataset) -> None:
    left, right = st.columns([2, 3], gap="large")
    with left, st.container(border=True):
        st.markdown("##### Forecast settings")
        horizon = st.select_slider("Horizon", [30, 60, 90, 120, 180], 90, format_func=lambda d: f"{d} days", key="cf_h")
        run_rate = st.toggle("Add typical unscheduled flows", True, help="Average of recent full months for costs and sales that have no uploaded bill or invoice (excluding one-offs, asset purchases and loans).", key="cf_rr")
        overdue = st.toggle("Assume overdue customers pay within 30 days", False, key="cf_od")
        delay = st.slider("Customers pay late by (days)", 0, 90, 0, 5, key="cf_delay")
        pct = st.slider("Share of pending invoices collected", 50, 100, 100, 5, format="%d%%", key="cf_pct")
        auto = default_buffer(ds.ledger, ds.as_of)
        buffer = st.number_input("Warn below (₹)", 0.0, value=float(round(auto, -3)), step=25_000.0, format="%.0f", key="cf_buf")
    opt = ForecastOptions(horizon_days=horizon, include_run_rate=run_rate, include_overdue_receivables=overdue,
                          receivable_delay_days=delay, receivable_collection_pct=float(pct), min_buffer=float(buffer))
    f = forecast_cash_flow(ds.ledger, ds.balances, ds.obligations, ds.as_of, opt)
    with right:
        if f["status"] != "ok":
            st.warning(f.get("message", "The forecast could not run."))
            return
        cols = st.columns(len(f["checkpoints"][:4]))
        for col, cp in zip(cols, f["checkpoints"][:4]):
            with col:
                c.kpi(f"In {cp['days']} days", c.inr(cp["balance"]), f"{cp['date']} · in {c.inr(cp['inflows'])} · out {c.inr(cp['outflows'])}", "projection", "est")
        daily = pd.DataFrame(f["daily"])
        fig = go.Figure()
        fig.add_scatter(x=daily["date"], y=daily["balance"], mode="lines", name="Projected balance", line=dict(color=INFLOW, width=2.4, shape="hv"),
                        customdata=daily[["inflow", "outflow"]], hovertemplate="%{x|%d %b %Y}<br>Balance ₹%{y:,.0f}<br>In ₹%{customdata[0]:,.0f} · Out ₹%{customdata[1]:,.0f}<extra></extra>")
        big = pd.DataFrame(f["scheduled_items"])
        if len(big):
            big = big[big["amount"].abs() >= 50_000]
            if len(big):
                pos = daily.set_index("date")["balance"]
                fig.add_scatter(x=big["date"], y=[pos.get(d) for d in big["date"]], mode="markers", name="Scheduled item ≥ ₹50K",
                                marker=dict(size=8, color=[INFLOW if a > 0 else OUTFLOW for a in big["amount"]], line=dict(color="white", width=1)),
                                customdata=big[["label", "amount"]], hovertemplate="%{x|%d %b}<br>%{customdata[0]}<br>₹%{customdata[1]:,.0f}<extra></extra>")
        fig.add_hline(y=buffer, line=dict(color=CAUTION, width=1.2, dash="dash"), annotation_text=f"Buffer {c.inr(buffer)}", annotation_position="bottom right", annotation_font_color=CAUTION)
        lakh_axis(fig, list(daily["balance"]) + [buffer, 0])
        plotly_layout(fig, 340)
        fig.update_layout(margin=dict(l=8, r=8, t=36, b=8))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        msg = f"Lowest projected balance: **{c.inr(f['lowest_balance'])}** on {f['lowest_balance_date']}."
        if f["first_negative_date"]:
            st.error(msg + f" Cash goes **negative on {f['first_negative_date']}**.")
        elif f["first_date_below_buffer"]:
            st.warning(msg + f" Falls below your buffer on {f['first_date_below_buffer']}.")
        else:
            st.success(msg + " Stays above your buffer throughout.")
        with st.expander(f"Scheduled items in the forecast ({len(f['scheduled_items'])})"):
            items = pd.DataFrame(f["scheduled_items"])
            if len(items):
                st.dataframe(items[["date", "label", "category", "kind", "amount"]], hide_index=True, use_container_width=True,
                             column_config={"amount": st.column_config.NumberColumn("Amount", format="₹%.0f")})
            if f["excluded_items"]:
                st.markdown("**Not counted**")
                st.dataframe(pd.DataFrame(f["excluded_items"]), hide_index=True, use_container_width=True)
        c.evidence_panel(f["evidence"], ds.obligations, title="Evidence: forecast method and assumptions", id_col="item_id", key="dl_cf")


def render() -> None:
    ds = state.current()
    c.header("Decision Lab", "Test a decision before you make it", f"{ds.name} · starting from cash on {ds.as_of.date():%d %b %Y}")
    if _cash_unknown(ds):
        return
    t1, t2 = st.tabs([":material/shopping_cart: Purchase simulator", ":material/timeline: Cash-flow scenarios"])
    with t1:
        _purchase_tab(ds)
    with t2:
        _cash_tab(ds)
    st.caption("Scenarios are arithmetic on the settings shown, not predictions. Your benefit estimates are not verified. Decision support only — not financial advice.")
