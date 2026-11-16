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
    "Generate the weekly Bollinger ranking workbook for the supplied NIFTY 750 universe. "
    "The report includes band values, the included weekly closes, and unavailable symbols."
)

period = int(st.session_state.get("bollinger_period", WeeklyBollingerService.DEFAULT_PERIOD))
multiplier = WeeklyBollingerService.DEFAULT_MULTIPLIER
report_end_date = st.date_input(
    "Report end date",
    value=date.today(),
    max_value=date.today(),
    help="The latest completed weekly candle on or before this date is used.",
)
target_week_end = WeeklyBollingerService.latest_completed_week_end(report_end_date)

if st.button("Generate Excel Report", type="primary"):
    current = get_weekly_bollinger_report()
    matches_snapshot = (
        current
        and current["latest_week_end"] == target_week_end
        and current["period"] == period
        and abs(current["multiplier"] - multiplier) < 1e-9
    )
    try:
        if not matches_snapshot:
            progress = st.progress(0, text="Starting report data refresh…")

            def update_progress(completed, total, symbol):
                interval = max(1, total // 100)
                if completed == total or completed % interval == 0:
                    progress.progress(
                        completed / total,
                        text=f"Fetched {completed} of {total} symbols · latest: {symbol}",
                    )

            with st.spinner("Fetching and calculating the requested weekly snapshot…"):
                refresh_weekly_bollinger_report(
                    period, multiplier, progress_callback=update_progress, as_of=report_end_date
                )
            progress.empty()

        report = get_weekly_bollinger_report()
        st.session_state["bollinger_generated_report"] = {
            "week_end": report["latest_week_end"],
            "period": report["period"],
            "multiplier": report["multiplier"],
            "filename": report["excel"]["filename"],
            "data": report["excel"]["data"],
            "universe_count": report["universe_count"],
            "eligible_count": len(report["results"]),
            "unavailable_count": len(report["unavailable"]),
            "unavailable": report["unavailable"],
        }
        st.success(f"Excel report generated for week ending {report['latest_week_end']:%d %b %Y}.")
    except Exception as exc:
        st.error(f"Report generation failed: {exc}")

generated = st.session_state.get("bollinger_generated_report")
if (generated and generated["week_end"] == target_week_end
        and generated["period"] == period
        and abs(generated["multiplier"] - multiplier) < 1e-9):
    st.download_button(
        "Download Excel Report",
        data=generated["data"],
        file_name=generated["filename"],
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    st.caption(
        f"Week ending {generated['week_end']:%d %b %Y} · {generated['eligible_count']} eligible · "
        f"{generated['unavailable_count']} unavailable · {generated['universe_count']} constituents"
    )
    if generated["unavailable"]:
        with st.expander(f"Unavailable or insufficient history ({generated['unavailable_count']})"):
            st.dataframe(pd.DataFrame(generated["unavailable"]).rename(columns={
                "symbol": "Stock Symbol", "company_name": "Company Name", "reason": "Reason",
            }), hide_index=True, width="stretch")
else:
    current = get_weekly_bollinger_report()
    if current and current["latest_week_end"] == target_week_end:
        st.info(
            f"A snapshot for week ending {target_week_end:%d %b %Y} is ready. "
            "Generate the workbook to download it."
        )
