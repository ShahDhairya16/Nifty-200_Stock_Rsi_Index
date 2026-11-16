import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from app.services.weekly_bollinger_service import WeeklyBollingerService
from frontend.utils.weekly_bollinger_report import (
    get_weekly_bollinger_report,
    refresh_weekly_bollinger_report,
)


st.title("Reports")
st.caption(
    "Generate the daily Bollinger report for the supplied NIFTY 750 universe. "
    "It includes band values, the configured trading-session closes, and unavailable symbols."
)

period = int(st.session_state.get("bollinger_period_daily", WeeklyBollingerService.DEFAULT_PERIOD))
multiplier = WeeklyBollingerService.DEFAULT_MULTIPLIER
report_end_date = st.date_input(
    "Report end date",
    value=date.today(),
    max_value=date.today(),
    help="The latest completed NSE trading session on or before this date is used.",
)
target_trade_date = WeeklyBollingerService.latest_completed_trade_date(report_end_date)

if st.button("Generate Excel Report", type="primary"):
    current = get_weekly_bollinger_report()
    matches_snapshot = (
        current
        and current["latest_trade_date"] == target_trade_date
        and current["period"] == period
        and abs(current["multiplier"] - multiplier) < 1e-9
    )
    try:
        if not matches_snapshot:
            progress = st.progress(0, text="Starting report data refresh…")

            def update_progress(completed, total, trade_date):
                interval = max(1, total // 100)
                if completed == total or completed % interval == 0:
                    progress.progress(
                        completed / total,
                        text=f"Fetched {completed} of {total} daily market files · latest: {trade_date}",
                    )

            with st.spinner("Fetching and calculating the requested daily snapshot…"):
                refresh_weekly_bollinger_report(
                    period, multiplier, progress_callback=update_progress, as_of=report_end_date
                )
            progress.empty()

        report = get_weekly_bollinger_report()
        with st.spinner("Preparing the Excel workbook…"):
            excel = WeeklyBollingerService.build_excel_report(report)
        st.session_state["nifty750_daily_generated_report_v2"] = {
            "trade_date": report["latest_trade_date"],
            "period": report["period"],
            "multiplier": report["multiplier"],
            "filename": excel["filename"],
            "data": excel["data"],
            "universe_count": report["universe_count"],
            "eligible_count": len(report["results"]),
            "unavailable_count": len(report["unavailable"]),
            "unavailable": report["unavailable"],
        }
        st.success(f"Excel report generated through {report['latest_trade_date']:%d %b %Y}.")
    except Exception as exc:
        st.error(f"Report generation failed: {exc}")

generated = st.session_state.get("nifty750_daily_generated_report_v2")
if (generated and generated["trade_date"] == target_trade_date
        and generated["period"] == period
        and abs(generated["multiplier"] - multiplier) < 1e-9):
    st.download_button(
        "Download Excel Report",
        data=generated["data"],
        file_name=generated["filename"],
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    st.caption(
        f"Through {generated['trade_date']:%d %b %Y} · {generated['eligible_count']} eligible · "
        f"{generated['unavailable_count']} unavailable · {generated['universe_count']} constituents"
    )
    if generated["unavailable"]:
        with st.expander(f"Unavailable or insufficient history ({generated['unavailable_count']})"):
            st.dataframe(pd.DataFrame(generated["unavailable"]).rename(columns={
                "symbol": "Stock Symbol", "company_name": "Company Name", "reason": "Reason",
            }), hide_index=True, width="stretch")
else:
    current = get_weekly_bollinger_report()
    if current and current["latest_trade_date"] == target_trade_date:
        st.info(
            f"A snapshot through {target_trade_date:%d %b %Y} is ready. "
            "Generate the workbook to download it."
        )
