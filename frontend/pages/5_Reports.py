import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from datetime import date
import streamlit as st
from frontend.components.sidebar import render_sidebar
from app.services.excel_report_service import ExcelReportService

STOCK_LIST_PATH = ROOT / "data" / "stocks.json"
REPORT_SOURCE_SIGNATURE = hashlib.sha256(
    b"pinned-nifty200-report-v2:" + STOCK_LIST_PATH.read_bytes()
).hexdigest()

render_sidebar()
st.title("Reports")
st.caption(
    "Generate the last 70 trading days and RSI ranking. "
    "Both sheets use the pinned NIFTY 200 constituent list from 15-Oct-2026."
)

# Streamlit can preserve session_state across source updates. Discard reports
# created before this report implementation or against a different universe.
if (
    st.session_state.get("latest_report")
    and st.session_state.get("latest_report_source_signature") != REPORT_SOURCE_SIGNATURE
):
    st.session_state.pop("latest_report", None)
    st.session_state.pop("latest_report_source_signature", None)
    st.info(
        "A previous report used an older stock list and was cleared. "
        "Generate a fresh report to download the corrected workbook."
    )

report_date = st.date_input(
    "Report end date",
    value=date.today(),
    max_value=date.today(),
    help="The workbook includes the 70 trading days ending on or before this date."
)

if st.button("Generate Excel Report", type="primary"):
    try:
        with st.spinner("Generating latest Excel report..."):
            result = ExcelReportService.generate_nifty200_excel_report(
                refresh_market_data=False,
                end_date=report_date,
                in_memory=True,
            )
        st.session_state["latest_report"] = result
        st.session_state["latest_report_source_signature"] = REPORT_SOURCE_SIGNATURE
        st.success(f"Report generated for {result['latest_trade_date']}.")
    except Exception:
        st.error("Excel report generation failed. Check the MongoDB settings and confirm that market data is available.")

result = st.session_state.get("latest_report")
if result and result.get("data"):
    st.download_button("Download Excel Report", data=result["data"],
                       file_name=result["filename"],
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.caption(f"{result['trading_days']} trading days | {result['stocks']} stocks")
