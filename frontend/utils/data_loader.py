import pandas as pd
import streamlit as st

from app.database.repositories import StockRepository, PriceRepository, RSIRepository


@st.cache_data(ttl=300, show_spinner=False)
def get_stock_list():
    stocks = StockRepository.get_all_stocks()
    return [
        {
            "id": index,
            "symbol": stock["symbol"],
            "company_name": stock.get("company_name") or stock["symbol"],
            "active": stock.get("active", True),
        }
        for index, stock in enumerate(stocks, 1)
    ]


@st.cache_data(ttl=300, show_spinner=False)
def get_rsi_ranking():
    return RSIRepository.get_latest_rsi_rankings()


@st.cache_data(ttl=300, show_spinner=False)
def get_dashboard_summary():
    ranking = get_rsi_ranking()
    active_count = StockRepository.count_stocks(active_only=True)
    latest_date = PriceRepository.latest_price_date()

    return {
        "active_stocks": active_count,
        "latest_date": latest_date,
        "highest_rsi": ranking["average_rsi"].max() if not ranking.empty else None,
        "lowest_rsi": ranking["average_rsi"].min() if not ranking.empty else None,
        "market_average": ranking["average_rsi"].mean() if not ranking.empty else None,
    }


@st.cache_data(ttl=300, show_spinner=False)
def get_stock_history(stock_id):
    stocks = StockRepository.get_all_stocks()
    if isinstance(stock_id, int) and 1 <= stock_id <= len(stocks):
        symbol = stocks[stock_id - 1]["symbol"]
    else:
        symbol = str(stock_id).strip().upper()

    prices = PriceRepository.get_prices_for_symbol(symbol)
    rsi = RSIRepository.get_rsi_for_symbol(symbol)

    if prices.empty:
        return pd.DataFrame()

    history = prices.merge(rsi, on=["symbol", "trade_date"], how="left")
    return history.drop(columns=["symbol"])


@st.cache_data(ttl=300, show_spinner=False)
def get_data_status():
    coverage = PriceRepository.get_price_coverage()
    active_stocks = StockRepository.count_stocks(active_only=True)
    total_stocks = StockRepository.count_stocks()
    inactive_stocks = total_stocks - active_stocks
    total_prices = PriceRepository.count_prices()
    total_rsi = RSIRepository.count_rsi()

    return {
        "coverage": coverage,
        "active_stocks": active_stocks,
        "inactive_stocks": inactive_stocks,
        "total_prices": total_prices,
        "total_rsi": total_rsi,
        "jobs": [],
        "errors": [],
    }


def refresh_data():
    st.cache_data.clear()
