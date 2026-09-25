import streamlit as st
from frontend.components.charts import rsi_distribution
from frontend.components.metrics import metric_row
from frontend.components.sidebar import render_sidebar
from frontend.components.tables import ranking_table
from frontend.utils.data_loader import get_dashboard_summary, get_rsi_ranking
from frontend.utils.formatters import format_date, format_number

render_sidebar()
st.title("NIFTY 200 RSI Dashboard")
st.caption("Market momentum analysis based on RSI 22, RSI 44 and RSI 66")

try:
    with st.spinner("Loading dashboard data..."):
        summary = get_dashboard_summary()
        ranking = get_rsi_ranking()
    metric_row([
        ("Active Stocks", f"{summary['active_stocks']:,}"),
        ("Latest Trading Date", format_date(summary["latest_date"])),
        ("Highest Average RSI", format_number(summary["highest_rsi"])),
        ("Lowest Average RSI", format_number(summary["lowest_rsi"])),
        ("Average Market RSI", format_number(summary["market_average"])),
    ])
    st.divider()
    left, right = st.columns(2)
    with left:
        st.subheader("Top 10 Stocks")
        ranking_table(ranking, 10)
    with right:
        st.subheader("Bottom 10 Stocks")
        ranking_table(ranking.sort_values("average_rsi", na_position="last"), 10)
    st.subheader("Average RSI Distribution")
    rsi_distribution(ranking.dropna(subset=["average_rsi"]))
except Exception:
    st.error("Unable to load dashboard data. Check the MongoDB settings in Streamlit Secrets or your local .env, then try again.")
