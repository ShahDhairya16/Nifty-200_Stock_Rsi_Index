import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from frontend.utils.weekly_bollinger_report import get_weekly_bollinger_report


st.title("NIFTY 750 Bollinger Rankings")
report = get_weekly_bollinger_report()
if not report:
    st.info("Refresh NIFTY 750 data from the sidebar to create a ranking.")
else:
    st.caption(
        f"Ranked across the complete supplied universe by how far the latest close is above the "
        f"middle band, in percent, highest first. Stocks below the middle band show negative values. "
        f"Latest completed trading session: {report['latest_trade_date']:%d %b %Y}."
    )
    search = st.text_input("Find a stock", placeholder="Enter symbol or company name")
    frame = pd.DataFrame(report["results"])
    if search:
        needle = search.casefold()
        frame = frame[
            frame["symbol"].str.casefold().str.contains(needle, na=False)
            | frame["company_name"].str.casefold().str.contains(needle, na=False)
        ]
    display = frame.rename(columns={
        "rank": "Rank", "symbol": "Stock Symbol", "company_name": "Company Name",
        "latest_close": "Latest Closing Price", "middle_band": "Middle Band",
        "close_vs_middle_pct": "% vs Middle Band",
        "standard_deviation": "Standard Deviation", "upper_band": "Upper Band",
        "lower_band": "Lower Band",
    })[["Rank", "Stock Symbol", "Company Name", "Latest Closing Price", "Middle Band",
       "% vs Middle Band", "Standard Deviation", "Upper Band", "Lower Band"]]
    st.dataframe(display, hide_index=True, width="stretch", column_config={
        "% vs Middle Band": st.column_config.NumberColumn(format="%+.2f%%"),
        **{name: st.column_config.NumberColumn(format="%.2f") for name in
           ["Latest Closing Price", "Middle Band", "Standard Deviation", "Upper Band", "Lower Band"]},
    })
    if report["unavailable"]:
        with st.expander(f"Unavailable or insufficient history ({len(report['unavailable'])})"):
            st.dataframe(pd.DataFrame(report["unavailable"]).rename(columns={
                "symbol": "Stock Symbol", "company_name": "Company Name", "reason": "Reason",
            }), hide_index=True, width="stretch")
