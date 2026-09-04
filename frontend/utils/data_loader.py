from datetime import date, timedelta
from pathlib import Path
import pandas as pd
import streamlit as st

from app.database.connection import get_db_session
from app.database.repositories import (
    DailyPriceRepository, JobErrorRepository, JobRunRepository,
    RSIMetricsRepository, StockRepository,
)


@st.cache_data(ttl=300, show_spinner=False)
def get_stock_list():
    with get_db_session() as session:
        return [{"id": stock.id, "symbol": stock.symbol,
                 "company_name": stock.company_name or stock.symbol,
                 "active": stock.active}
                for stock in StockRepository.get_all_stocks(session)]


@st.cache_data(ttl=300, show_spinner=False)
def get_rsi_ranking():
    with get_db_session() as session:
        return pd.DataFrame(RSIMetricsRepository.get_latest_rsi_rankings(session))


@st.cache_data(ttl=300, show_spinner=False)
def get_dashboard_summary():
    ranking = get_rsi_ranking()
    stocks = pd.DataFrame(get_stock_list())
    latest_date = None
    with get_db_session() as session:
        latest_date = DailyPriceRepository.get_latest_price_date(session)
    return {
        "active_stocks": int(stocks["active"].sum()) if not stocks.empty else 0,
        "latest_date": latest_date,
        "highest_rsi": ranking["average_rsi"].max() if not ranking.empty else None,
        "lowest_rsi": ranking["average_rsi"].min() if not ranking.empty else None,
        "market_average": ranking["average_rsi"].mean() if not ranking.empty else None,
    }


@st.cache_data(ttl=300, show_spinner=False)
def get_stock_history(stock_id):
    with get_db_session() as session:
        return pd.DataFrame(DailyPriceRepository.get_stock_history_with_rsi(session, stock_id))


@st.cache_data(ttl=300, show_spinner=False)
def get_data_status():
    with get_db_session() as session:
        coverage = DailyPriceRepository.get_price_coverage(session)
        stocks = [{"symbol": stock.symbol, "active": stock.active}
                  for stock in StockRepository.get_all_stocks(session)]
        jobs = JobRunRepository.get_recent_job_runs(session)
        errors = JobErrorRepository.get_recent_errors(session)
    coverage_df = pd.DataFrame(coverage)
    if not coverage_df.empty:
        active_by_symbol = {stock["symbol"]: stock["active"] for stock in stocks}
        coverage_df["active"] = coverage_df["symbol"].map(active_by_symbol).fillna(False)
    return {
        "coverage": coverage_df,
        "active_stocks": sum(stock["active"] for stock in stocks),
        "inactive_stocks": sum(not stock["active"] for stock in stocks),
        "total_prices": int(coverage_df["price_count"].sum()) if not coverage_df.empty else 0,
        "total_rsi": int(coverage_df["rsi_count"].sum()) if not coverage_df.empty else 0,
        "jobs": jobs,
        "errors": errors,
    }


def refresh_data():
    st.cache_data.clear()
