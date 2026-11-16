import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import plotly.express as px
import streamlit as st

from frontend.utils.weekly_bollinger_report import get_weekly_bollinger_report


st.title("NIFTY 750 Bollinger Dashboard")
st.caption(
    "55 completed weekly closes per stock, built from the final NSE trading-day close "
    "in each week. The current incomplete week is excluded; bands use population standard deviation."
)
report = get_weekly_bollinger_report()
if not report:
    st.info("Use **Refresh NIFTY 750 data** in the sidebar to load the latest dashboard snapshot.")
else:
    results = report["results"]
    eligible = len(results)
    unavailable = len(report["unavailable"])
    metric_cols = st.columns(4)
    metric_cols[0].metric("Universe symbols", report["universe_count"])
    metric_cols[1].metric("Eligible stocks", eligible)
    metric_cols[2].metric("Unavailable / insufficient", unavailable)
    metric_cols[3].metric("Latest completed week", report["latest_week_end"].strftime("%d %b %Y"))
    st.caption(
        f"Snapshot settings: {report['period']} weeks · {report['multiplier']:g}σ · "
        f"{report['history_start_date']:%d %b %Y} history start"
    )

    if results:
        st.subheader("Highest Upper Bands")
        top = pd.DataFrame(results[:15])
        chart = px.bar(top.sort_values("upper_band"), x="upper_band", y="symbol", orientation="h",
                       labels={"upper_band": "Upper Band", "symbol": "Stock Symbol"},
                       color="upper_band", color_continuous_scale="Blues")
        chart.update_layout(showlegend=False, coloraxis_showscale=False, height=520,
                            yaxis_title=None, xaxis_title="Upper Band")
        st.plotly_chart(chart, width="stretch")
        st.dataframe(pd.DataFrame([{
            "Rank": row["rank"], "Stock Symbol": row["symbol"],
            "Latest Closing Price": row["latest_close"], "Middle Band": row["middle_band"],
            "Upper Band": row["upper_band"], "Lower Band": row["lower_band"],
        } for row in results[:10]]), hide_index=True, width="stretch", column_config={
            name: st.column_config.NumberColumn(format="%.2f") for name in
            ["Latest Closing Price", "Middle Band", "Upper Band", "Lower Band"]
        })
    else:
        st.warning("No stocks currently have all required weekly closes.")
