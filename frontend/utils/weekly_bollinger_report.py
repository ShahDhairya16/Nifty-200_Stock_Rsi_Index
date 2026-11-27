from datetime import date
import hashlib
import json

import streamlit as st

from app.services.weekly_bollinger_service import WeeklyBollingerService


REPORT_KEY = "nifty750_daily_bollinger_report_v2"


def stock_universe_signature(universe) -> str:
    """Identify the exact symbol/series mapping used by a cached report."""
    payload = sorted(
        (str(stock["symbol"]).strip().upper(), str(stock.get("series") or "EQ").strip().upper())
        for stock in universe
    )
    return hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode("utf-8")).hexdigest()


def refresh_weekly_bollinger_report(period: int, multiplier: float,
                                    progress_callback=None, as_of: date = None,
                                    universe=None) -> None:
    """Fetch, calculate, and cache one report for all NIFTY 750 pages in session."""
    if universe is None:
        universe = WeeklyBollingerService.fetch_stock_universe()
    report = WeeklyBollingerService.calculate_universe(
        universe, period=period, multiplier=multiplier, as_of=as_of,
        progress_callback=progress_callback,
    )
    report["universe_signature"] = stock_universe_signature(universe)
    st.session_state[REPORT_KEY] = report


def get_weekly_bollinger_report():
    report = st.session_state.get(REPORT_KEY)
    if report and report.get("ranking_basis") != WeeklyBollingerService.RANKING_BASIS:
        # A snapshot made before the ranking change already holds every value
        # needed, so re-rank it instead of forcing a new NSE download.
        report["results"] = WeeklyBollingerService.sort_results(report["results"])
        report["ranking_basis"] = WeeklyBollingerService.RANKING_BASIS
    return report
