import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

st.set_page_config(page_title="NIFTY Analytics", page_icon="📊",
                   layout="wide", initial_sidebar_state="expanded")


project = st.session_state.get("selected_project", "home")

if project == "home":
    navigation = st.navigation(
        [st.Page("pages/0_Project_Home.py", title="Choose a project", icon="🏠")],
        position="hidden",
    )
elif project == "nifty200":
    navigation = st.navigation({
        "NIFTY 750 RSI": [
            st.Page("pages/1_Dashboard.py", title="Dashboard", icon="📊", default=True),
            st.Page("pages/2_RSI_Ranking.py", title="RSI Ranking", icon="🏆"),
            st.Page("pages/3_Stock_Analysis.py", title="Stock Analysis", icon="📈"),
            st.Page("pages/4_AI_Advisor.py", title="AI Advisor", icon="🤖"),
            st.Page("pages/5_Reports.py", title="Reports", icon="📥"),
        ]
    }, position="sidebar", expanded=True)
elif project == "nifty750":
    from app.services.weekly_bollinger_service import WeeklyBollingerService

    navigation = st.navigation({
        "NIFTY 750 Bollinger": [
            st.Page("pages/6_Weekly_Bollinger.py", title="Dashboard", icon="📊", default=True),
            st.Page("pages/7_Bollinger_Rankings.py", title="Rankings", icon="🏆"),
            st.Page("pages/8_Bollinger_Analysis.py", title="Analysis", icon="📈"),
            st.Page("pages/9_Bollinger_Reports.py", title="Reports", icon="📥"),
        ]
    }, position="sidebar", expanded=True)
    from frontend.utils.weekly_bollinger_report import (
        get_weekly_bollinger_report,
        refresh_weekly_bollinger_report,
    )

    with st.sidebar:
        st.markdown("## NIFTY 750")
        st.caption("Daily Bollinger Band strategy")
        if st.button("← Choose project", width="stretch"):
            st.session_state["selected_project"] = "home"
            st.rerun()
        st.divider()
        period = st.number_input("Working days", min_value=2, max_value=1000,
                                 value=55, step=1, key="bollinger_period_daily")
        multiplier = WeeklyBollingerService.DEFAULT_MULTIPLIER
        st.caption(f"Standard deviation multiplier: fixed at {multiplier:g}×")
        if st.button("Refresh NIFTY 750 data", type="primary", width="stretch"):
            try:
                progress = st.progress(0, text="Starting NIFTY 750 data refresh…")

                def update_progress(completed, total, trade_date):
                    update_interval = max(1, total // 100)
                    if completed == total or completed % update_interval == 0:
                        progress.progress(
                            completed / total,
                            text=f"Fetched {completed} of {total} daily market files · latest: {trade_date}",
                        )

                with st.spinner("Fetching daily market files for the NIFTY 750 universe…"):
                    refresh_weekly_bollinger_report(
                        int(period), float(multiplier), progress_callback=update_progress
                    )
                progress.empty()
                st.success("Bollinger report refreshed.")
            except Exception as exc:
                st.error(f"Refresh failed: {exc}")
        report = get_weekly_bollinger_report()
        if report:
            st.caption(
                f"Latest completed session: {report['latest_trade_date']:%d %b %Y} · "
                f"{len(report['results'])} eligible / {report['universe_count']} constituents"
            )
            if report["period"] != int(period) or abs(report["multiplier"] - multiplier) > 1e-9:
                st.warning(
                    f"Current snapshot uses {report['period']} working days and "
                    f"{report['multiplier']:g}×. Refresh to apply the current settings."
                )
        else:
            st.info("Refresh data to populate the dashboard, rankings, analysis, and Excel report.")
else:
    st.session_state["selected_project"] = "home"
    st.rerun()

navigation.run()
