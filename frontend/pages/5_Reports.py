from pathlib import Path
from datetime import date
import streamlit as st
from frontend.components.sidebar import render_sidebar
from app.services.excel_report_service import ExcelReportService

render_sidebar()
st.title("Reports")
st.caption("Generate the backend-produced workbook containing the last 70 trading days and RSI ranking.")

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
                end_date=report_date
            )
        st.session_state["latest_report"] = result
        st.success(f"Report generated for {result['latest_trade_date']}.")
    except Exception:
        st.error("Excel report generation failed. Please verify that the database service is running and data is available.")

result = st.session_state.get("latest_report")
if result and Path(result["file_path"]).exists():
    report_path = Path(result["file_path"])
    st.download_button("Download Excel Report", data=report_path.read_bytes(),
                       file_name=result["filename"],
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.caption(f"{result['trading_days']} trading days | {result['stocks']} stocks")