"""Visual design: one stylesheet and the chart palette, shared by every page."""

from __future__ import annotations

import streamlit as st

# Chart colours (validated categorical pair: blue for money in, orange for money out).
INFLOW = "#2a78d6"
OUTFLOW = "#eb6834"
NEUTRAL = "#64748b"
GRID = "#e5e7eb"
GOOD = "#0b6e4f"
CAUTION = "#b45309"
BAD = "#b42318"

CSS = """
<style>
:root {
  --ink: #111827; --ink-2: #374151; --ink-3: #6b7280; --line: #e5e7eb; --surface: #ffffff;
  --canvas: #f6f7f9; --brand: #0b6e4f; --brand-50: #e8f5ef; --caution: #b45309; --caution-50: #fff7e6;
  --bad: #b42318; --bad-50: #fdecea; --agent: #1e5b8a; --agent-50: #eaf2f9;
}
html, body, [class*="css"] { font-feature-settings: "tnum" 1; }
.block-container { padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1280px; }
h1, h2, h3 { letter-spacing: -0.01em; color: var(--ink); }
[data-testid="stSidebar"] { background: #0f1b2d; }
[data-testid="stSidebar"] * { color: #e5e9f0; }
[data-testid="stSidebar"] .stSelectbox label, [data-testid="stSidebar"] .stDateInput label { color: #aab4c3 !important; }
[data-testid="stSidebarNav"] a span { font-weight: 500; }
[data-testid="stSidebar"] [data-baseweb="select"] > div, [data-testid="stSidebar"] [data-baseweb="input"],
[data-testid="stSidebar"] .react-aria-ComboBox [role="group"], [data-testid="stSidebar"] [data-testid="stDateInput"] [role="group"] { background: #1a2a42 !important; border-color: #2c3e5c !important; }
[data-testid="stSidebar"] input { color: #f1f5f9 !important; -webkit-text-fill-color: #f1f5f9 !important; }
[data-testid="stSidebar"] [data-baseweb="select"] *, [data-testid="stSidebar"] [data-baseweb="input"] input { color: #f1f5f9 !important; -webkit-text-fill-color: #f1f5f9 !important; }
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] { color: #aab4c3 !important; }
.fp-brand { display:flex; align-items:center; gap:.6rem; font-weight:700; font-size:1.15rem; margin:.2rem 0 1rem; color:#fff; }
.fp-brand .dot { width:28px; height:28px; border-radius:8px; background:linear-gradient(135deg,#18a874,#0b6e4f); display:inline-flex; align-items:center; justify-content:center; font-size:.85rem; }
.fp-eyebrow { font-size:.78rem; font-weight:600; text-transform:uppercase; letter-spacing:.06em; color: var(--brand); margin-bottom:.15rem; }
.fp-sub { color: var(--ink-3); margin-top:-.4rem; margin-bottom:1rem; font-size:.95rem; }
.fp-card { background: var(--surface); border:1px solid var(--line); border-radius:14px; padding:1rem 1.1rem; height:100%; box-shadow: 0 1px 2px rgba(16,24,40,.04); }
.fp-kpi-label { color: var(--ink-3); font-size:.82rem; font-weight:500; display:flex; align-items:center; gap:.35rem; }
.fp-kpi-value { font-size:1.6rem; font-weight:700; color: var(--ink); line-height:1.25; margin-top:.15rem; white-space:nowrap; }
.fp-kpi-note { color: var(--ink-3); font-size:.78rem; margin-top:.25rem; }
.fp-tag { display:inline-block; font-size:.68rem; font-weight:600; padding:.08rem .45rem; border-radius:999px; background:#eef2f7; color:#475569; text-transform:uppercase; letter-spacing:.03em; }
.fp-tag.est { background: var(--caution-50); color: var(--caution); }
.fp-tag.verified { background: var(--brand-50); color: var(--brand); }
.fp-alert { display:flex; gap:.7rem; padding:.75rem .9rem; border-radius:12px; border:1px solid var(--line); background: var(--surface); margin-bottom:.5rem; }
.fp-alert .bar { width:4px; border-radius:4px; flex-shrink:0; }
.fp-alert.bad .bar { background: var(--bad); } .fp-alert.caution .bar { background: var(--caution); } .fp-alert.info .bar { background: var(--agent); }
.fp-alert .t { font-weight:600; color: var(--ink); font-size:.92rem; }
.fp-alert .d { color: var(--ink-2); font-size:.86rem; }
.fp-tool { border-left:3px solid var(--agent); background: var(--agent-50); padding:.45rem .7rem; border-radius:0 8px 8px 0; margin:.25rem 0; font-size:.85rem; }
.fp-tool code { background: transparent; color: var(--agent); font-weight:600; }
.fp-verdict { border-radius:14px; padding:1rem 1.2rem; border:1px solid var(--line); background: var(--surface); }
.fp-verdict.good { border-left:5px solid var(--brand); } .fp-verdict.caution { border-left:5px solid var(--caution); } .fp-verdict.bad { border-left:5px solid var(--bad); }
.fp-muted { color: var(--ink-3); font-size:.85rem; }
div[data-testid="stExpander"] { border-radius: 12px; background: var(--surface); }
div[data-testid="stMetric"] { background: var(--surface); border:1px solid var(--line); border-radius:14px; padding:.8rem 1rem; }
@media (max-width: 900px) { .fp-kpi-value { font-size:1.3rem; } }
</style>
"""


def apply() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def plotly_layout(fig, height: int = 320):
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=8, t=8, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, -apple-system, Segoe UI, sans-serif", size=12, color="#374151"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, title_text=""),
        hoverlabel=dict(bgcolor="white", font_size=12),
    )
    fig.update_xaxes(showgrid=False, linecolor=GRID, tickfont=dict(color="#6b7280"))
    fig.update_yaxes(gridcolor=GRID, zeroline=True, zerolinecolor="#cbd5e1", tickfont=dict(color="#6b7280"))
    return fig


def lakh_axis(fig, values, axis: str = "y") -> None:
    """Ticks in Indian units (₹50K, ₹5L, ₹1.2Cr) instead of Plotly's 1M / 0.5M."""
    import math

    vals = [abs(v) for v in values if v is not None]
    lo = min([0.0] + [v for v in values if v is not None])
    hi = max(vals + [1.0])
    raw = (hi - min(lo, 0)) / 5
    mag = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    start = math.floor(lo / step) * step
    ticks = []
    t = start
    while t <= hi + step * 0.01:
        ticks.append(t)
        t += step

    def label(x: float) -> str:
        a, sign = abs(x), "−" if x < 0 else ""
        if a >= 1e7:
            return f"{sign}₹{a / 1e7:g}Cr"
        if a >= 1e5:
            return f"{sign}₹{a / 1e5:g}L"
        if a >= 1e3:
            return f"{sign}₹{a / 1e3:g}K"
        return f"{sign}₹{a:g}"

    getattr(fig, f"update_{axis}axes")(tickvals=ticks, ticktext=[label(x) for x in ticks])
