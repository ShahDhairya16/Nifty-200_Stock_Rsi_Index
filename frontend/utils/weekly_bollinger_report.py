from datetime import date
from functools import lru_cache

import streamlit as st

from app.services.nse_client import NSEClient
from app.services.weekly_bollinger_service import WeeklyBollingerService


REPORT_KEY = "weekly_bollinger_report"


@lru_cache(maxsize=1500)
def _cached_history(symbol: str, start_date: date, end_date: date):
    """Reuse identical symbol/date requests across refreshes in this process."""
    return NSEClient.get_stock_historical_data(symbol, start_date, end_date)


def refresh_weekly_bollinger_report(period: int, multiplier: float,
                                    progress_callback=None, as_of: date = None) -> None:
    """Fetch, calculate, and cache one report for all NIFTY 750 pages in session."""
    universe = WeeklyBollingerService.fetch_stock_universe()
    report = WeeklyBollingerService.calculate_universe(
        universe, period=period, multiplier=multiplier, as_of=as_of or date.today(),
        history_fetcher=_cached_history, progress_callback=progress_callback,
    )
    report["excel"] = WeeklyBollingerService.build_excel_report(report)
    st.session_state[REPORT_KEY] = report


def get_weekly_bollinger_report():
    return st.session_state.get(REPORT_KEY)
