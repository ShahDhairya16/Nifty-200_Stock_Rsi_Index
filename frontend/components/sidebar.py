import streamlit as st
from frontend.utils.data_loader import get_dashboard_summary, refresh_data
from frontend.utils.formatters import format_date
from frontend.components.theme import apply_theme


def render_sidebar():
    apply_theme()
    with st.sidebar:
        st.markdown("## NIFTY 200")
        st.caption("RSI analytics workspace")
        st.divider()
        if st.button("Refresh dashboard data", use_container_width=True):
            refresh_data()
            st.rerun()
        try:
            st.caption(f"Latest data date\n{format_date(get_dashboard_summary()['latest_date'])}")
        except Exception:
            st.caption("Latest data date\nUnavailable")