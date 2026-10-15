"""FinPilot AI — agentic financial copilot for Indian small businesses. Run: streamlit run app.py"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from finpilot.config import settings
from finpilot.ui import state, theme

ASSETS = Path(__file__).parent / "assets"
st.set_page_config(page_title="FinPilot AI", page_icon=str(ASSETS / "icon.svg"), layout="wide", initial_sidebar_state="expanded")
st.logo(str(ASSETS / "logo.svg"), size="large", icon_image=str(ASSETS / "icon.svg"))
theme.apply()


def overview():
    from finpilot.ui import overview as page

    page.render()


def ask():
    from finpilot.ui import ask as page

    page.render()


def lab():
    from finpilot.ui import decision_lab as page

    page.render()


def data():
    from finpilot.ui import data_page as page

    page.render()


pages = st.navigation(
    [
        st.Page(overview, title="Overview", icon=":material/space_dashboard:", url_path="overview", default=True),
        st.Page(ask, title="Ask FinPilot", icon=":material/forum:", url_path="ask"),
        st.Page(lab, title="Decision Lab", icon=":material/science:", url_path="decision-lab"),
        st.Page(data, title="Data & uploads", icon=":material/upload_file:", url_path="data"),
    ]
)

with st.sidebar:
    has_upload = state.uploaded_dataset() is not None
    # A saved upload is the default for a new session; the demo otherwise.
    st.session_state.setdefault("data_source", "upload" if has_upload else "demo")
    choices = ["demo"] + (["upload"] if has_upload else [])
    if st.session_state["data_source"] not in choices:
        st.session_state["data_source"] = "demo"
    labels = {"demo": "Demo business (fictional)", "upload": "My uploaded data"}
    st.selectbox(
        "Data",
        choices,
        format_func=labels.get,
        key="data_source",
    )
    ds = state.current()
    if not ds.is_demo:
        st.date_input("Figures as of", value=ds.as_of.date(), key="as_of_override")
    else:
        st.caption(f"As of {ds.as_of.date():%d %b %Y} (fixed for a repeatable demo)")
    cfg = settings()
    st.caption(
        f"AI: {'on — ' + cfg.model if cfg.ai_enabled else 'off — rule-based mode'}  \n"
        "Calculations always run locally in Python."
    )
    st.caption("Decision support, not financial advice. FinPilot never makes payments or filings.")

pages.run()
