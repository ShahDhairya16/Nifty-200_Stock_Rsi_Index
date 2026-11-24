from datetime import date

import streamlit as st

from app.services.weekly_bollinger_service import WeeklyBollingerService


REPORT_KEY = "nifty750_daily_bollinger_report_v2"


def refresh_weekly_bollinger_report(period: int, multiplier: float,
                                    progress_callback=None, as_of: date = None) -> None:
    """Fetch, calculate, and cache one report for all NIFTY 750 pages in session."""
    universe = WeeklyBollingerService.fetch_stock_universe()
    report = WeeklyBollingerService.calculate_universe(
        universe, period=period, multiplier=multiplier, as_of=as_of,
        progress_callback=progress_callback,
    )
    st.session_state[REPORT_KEY] = report


def get_weekly_bollinger_report():
    report = st.session_state.get(REPORT_KEY)
    if report and report.get("ranking_basis") != WeeklyBollingerService.RANKING_BASIS:
        # A snapshot made before the ranking change already holds every value
        # needed, so re-rank it instead of forcing a new NSE download.
        report["results"] = WeeklyBollingerService.sort_results(report["results"])
        report["ranking_basis"] = WeeklyBollingerService.RANKING_BASIS
    return report
