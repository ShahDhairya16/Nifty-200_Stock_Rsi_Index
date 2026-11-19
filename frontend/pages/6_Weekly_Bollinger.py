import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import plotly.express as px
import streamlit as st

from app.services.weekly_bollinger_service import WeeklyBollingerService
from frontend.utils.weekly_bollinger_report import (
    get_weekly_bollinger_report,
    refresh_weekly_bollinger_report,
)


st.title("NIFTY 750 Bollinger Dashboard")
st.caption(
    "The default window is each stock’s last 55 completed NSE trading-session closes, with population variance "
    "and a fixed 3.7 multiplier: Upper/Lower Band = Middle Band ± 3.7 × Standard Deviation."
)
report = get_weekly_bollinger_report()
if not report:
    with st.container(border=True):
        st.subheader("Load the latest dashboard snapshot")
        st.caption("The refresh fetches daily market-wide NSE files and aligns the last 55 sessions.")
        if st.button("Load NIFTY 750 Dashboard", type="primary"):
            progress = st.progress(0, text="Starting NIFTY 750 data refresh…")

            def update_progress(completed, total, symbol):
                interval = max(1, total // 100)
                if completed == total or completed % interval == 0:
                    progress.progress(
                        completed / total,
                        text=f"Fetched {completed} of {total} daily market files · latest: {symbol}",
                    )

            try:
                with st.spinner("Fetching and calculating the latest daily snapshot…"):
                    refresh_weekly_bollinger_report(
                        int(st.session_state.get("bollinger_period_daily", WeeklyBollingerService.DEFAULT_PERIOD)),
                        WeeklyBollingerService.DEFAULT_MULTIPLIER,
                        progress_callback=update_progress,
                    )
                st.rerun()
            except Exception as exc:
                st.error(f"Dashboard refresh failed: {exc}")
else:
    results = report["results"]
    eligible = len(results)
    unavailable = len(report["unavailable"])
    metric_cols = st.columns(4)
    metric_cols[0].metric("Universe symbols", report["universe_count"])
    metric_cols[1].metric("Eligible stocks", eligible)
    metric_cols[2].metric("Unavailable / insufficient", unavailable)
    metric_cols[3].metric("Latest completed session", report["latest_trade_date"].strftime("%d %b %Y"))
    st.caption(
        f"Snapshot settings: {report['period']} working days · {report['multiplier']:g}σ · "
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
        st.warning("No stocks currently have all required daily closes.")
