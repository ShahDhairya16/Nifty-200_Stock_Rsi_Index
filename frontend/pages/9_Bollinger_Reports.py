import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from frontend.utils.weekly_bollinger_report import get_weekly_bollinger_report


st.title("NIFTY 750 Bollinger Reports")
report = get_weekly_bollinger_report()
if not report:
    st.info("Refresh NIFTY 750 data from the sidebar to generate the Excel report.")
else:
    st.caption(
        f"Workbook snapshot for the week ending {report['latest_week_end']:%d %b %Y}; "
        f"{report['period']} weekly closes and {report['multiplier']:g}σ multiplier."
    )
    st.download_button(
        "Download Excel workbook", data=report["excel"]["data"],
        file_name=report["excel"]["filename"],
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )
    st.markdown(
        "The workbook includes the ranked bands, all included weekly closes, "
        "unavailable symbols and run settings."
    )
    summary = pd.DataFrame([
        {"Metric": "Supplied universe", "Value": report["universe_count"]},
        {"Metric": "Eligible stocks", "Value": len(report["results"])},
        {"Metric": "Unavailable / insufficient", "Value": len(report["unavailable"])},
        {"Metric": "History start", "Value": report["history_start_date"].isoformat()},
        {"Metric": "Latest completed week", "Value": report["latest_week_end"].isoformat()},
        {"Metric": "Weekly periods", "Value": report["period"]},
        {"Metric": "Standard deviation multiplier", "Value": report["multiplier"]},
    ])
    st.dataframe(summary, hide_index=True, width="stretch")
    if report["unavailable"]:
        with st.expander(f"Unavailable or insufficient history ({len(report['unavailable'])})"):
            st.dataframe(pd.DataFrame(report["unavailable"]).rename(columns={
                "symbol": "Stock Symbol", "company_name": "Company Name", "reason": "Reason",
            }), hide_index=True, width="stretch")
