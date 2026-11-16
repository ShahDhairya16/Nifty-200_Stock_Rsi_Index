import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from app.services.weekly_bollinger_service import WeeklyBollingerService

with st.sidebar:
    st.markdown("## NIFTY 750")
    st.caption("Weekly Bollinger Band strategy")
    if st.button("← Choose project", width="stretch"):
        st.session_state["selected_project"] = "home"
        st.rerun()

st.title("NIFTY 750 Weekly Bollinger Bands")
st.caption(
    "Uses the supplied data/ind_niftytotalmarket_list.xlsx universe. Weekly candles are built "
    "from the final NSE trading-day close in each Monday–Sunday week. The current "
    "incomplete week is excluded; population standard deviation is used. The calculation "
    "uses exactly 55 consecutive completed weekly closes (about 385 calendar days), "
    "with a six-week history buffer for holidays and missing records."
)

period_col, multiplier_col = st.columns(2)
with period_col:
    period = st.number_input("Completed weeks", min_value=2, max_value=260, value=55, step=1)
with multiplier_col:
    multiplier = st.number_input("Standard deviation multiplier", min_value=0.0, value=1.0,
                                 max_value=10.0, step=0.5)

if st.button("Refresh NIFTY 750 calculation", type="primary"):
    st.session_state.pop("weekly_bollinger_report", None)
    try:
        with st.spinner("Fetching the live universe and calculating weekly prices. This may take several minutes..."):
            universe = WeeklyBollingerService.fetch_stock_universe()
            report = WeeklyBollingerService.calculate_universe(
                universe, period=int(period), multiplier=float(multiplier), as_of=date.today()
            )
            report["company_names"] = {item["symbol"]: item.get("company_name", item["symbol"])
                                       for item in universe}
            report["excel"] = WeeklyBollingerService.build_excel_report(report)
        st.session_state["weekly_bollinger_report"] = report
    except Exception as exc:
        st.error(f"Unable to generate the NIFTY 750 report: {exc}")

report = st.session_state.get("weekly_bollinger_report")
if report:
    st.success(
        f"Latest completed weekly candle: {report['latest_week_end']:%d %b %Y} · "
        f"{len(report['results'])} eligible · {len(report['unavailable'])} unavailable · "
        f"{report['universe_count']} constituents"
    )
    st.download_button(
        "Download Excel workbook", data=report["excel"]["data"],
        file_name=report["excel"]["filename"],
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )
    st.subheader("Ranked stocks")
    if report["results"]:
        frame = pd.DataFrame(report["results"]).rename(columns={
            "rank": "Rank", "symbol": "Stock Symbol", "latest_close": "Latest Closing Price",
            "middle_band": "Middle Band", "standard_deviation": "Standard Deviation",
            "upper_band": "Upper Band", "lower_band": "Lower Band",
        })[["Rank", "Stock Symbol", "Latest Closing Price", "Middle Band",
           "Standard Deviation", "Upper Band", "Lower Band"]]
        st.dataframe(frame, hide_index=True, width="stretch", column_config={
            name: st.column_config.NumberColumn(format="%.2f") for name in
            ["Latest Closing Price", "Middle Band", "Standard Deviation", "Upper Band", "Lower Band"]
        })
    else:
        st.warning("No stocks had enough valid weekly history to calculate bands.")
    if report["unavailable"]:
        st.subheader("Stocks with unavailable or insufficient history")
        st.dataframe(pd.DataFrame(report["unavailable"]).rename(columns={
            "symbol": "Stock Symbol", "company_name": "Company Name", "reason": "Reason",
        }), hide_index=True, width="stretch")
