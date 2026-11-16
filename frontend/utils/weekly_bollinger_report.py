from datetime import date

import streamlit as st

from app.services.weekly_bollinger_service import WeeklyBollingerService


REPORT_KEY = "weekly_bollinger_report"


def refresh_weekly_bollinger_report(period: int, multiplier: float) -> None:
    """Fetch, calculate, and cache one report for all NIFTY 750 pages in session."""
    universe = WeeklyBollingerService.fetch_stock_universe()
    report = WeeklyBollingerService.calculate_universe(
        universe, period=period, multiplier=multiplier, as_of=date.today()
    )
    report["excel"] = WeeklyBollingerService.build_excel_report(report)
    st.session_state[REPORT_KEY] = report


def get_weekly_bollinger_report():
    return st.session_state.get(REPORT_KEY)
