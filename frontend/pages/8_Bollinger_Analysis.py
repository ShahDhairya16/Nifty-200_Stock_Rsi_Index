import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from frontend.utils.weekly_bollinger_report import get_weekly_bollinger_report


st.title("NIFTY 750 Stock Analysis")
report = get_weekly_bollinger_report()
if not report:
    st.info("Refresh NIFTY 750 data from the sidebar to analyze a stock.")
elif not report["results"]:
    st.warning("No stocks have all required daily closes for analysis.")
else:
    by_symbol = {row["symbol"]: row for row in report["results"]}
    selected_symbol = st.selectbox("Stock", list(by_symbol), format_func=lambda s: f"{s} — {by_symbol[s]['company_name']}")
    stock = by_symbol[selected_symbol]
    cols = st.columns(5)
    cols[0].metric("Rank", f"#{stock['rank']}")
    cols[1].metric("Latest Close", f"{stock['latest_close']:.2f}")
    cols[2].metric("Middle Band", f"{stock['middle_band']:.2f}")
    cols[3].metric("Upper Band", f"{stock['upper_band']:.2f}")
    cols[4].metric("Lower Band", f"{stock['lower_band']:.2f}")
    st.caption(
        f"{stock['observations_used']} daily closes through "
        f"{report['latest_trade_date']:%d %b %Y} · σ={stock['standard_deviation']:.2f} · "
        f"multiplier={report['multiplier']:g}"
    )

    dates = stock["price_dates"]
    chart = go.Figure()
    chart.add_trace(go.Scatter(x=dates, y=stock["daily_closes"], mode="lines",
                               name="Daily Close", line={"color": "#2563eb"}))
    chart.add_hline(y=stock["upper_band"], line_dash="dash", line_color="#dc2626",
                    annotation_text="Upper Band")
    chart.add_hline(y=stock["middle_band"], line_dash="dot", line_color="#64748b",
                    annotation_text="Middle Band")
    chart.add_hline(y=stock["lower_band"], line_dash="dash", line_color="#16a34a",
                    annotation_text="Lower Band")
    chart.update_layout(height=480, xaxis_title="Trading date", yaxis_title="Price",
                        legend={"orientation": "h", "y": 1.12})
    st.plotly_chart(chart, width="stretch")
    detail = pd.DataFrame({"Trading Date": dates, "Daily Close": stock["daily_closes"]})
    st.dataframe(detail, hide_index=True, width="stretch", column_config={
        "Daily Close": st.column_config.NumberColumn(format="%.2f")
    })
