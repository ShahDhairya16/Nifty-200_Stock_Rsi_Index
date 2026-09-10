import pandas as pd
import streamlit as st

from app.file_store import FileStore


@st.cache_data(ttl=300, show_spinner=False)
def get_stock_list():
    return [{"id": index, "symbol": stock["symbol"], "company_name": stock.get("company_name") or stock["symbol"], "active": stock.get("active", True)}
            for index, stock in enumerate(FileStore.load_stocks(), 1)]


@st.cache_data(ttl=300, show_spinner=False)
def get_rsi_ranking():
    stocks = {stock["symbol"]: stock for stock in FileStore.active_stocks()}
    rsi = FileStore.load_rsi()
    if rsi.empty:
        return pd.DataFrame()
    latest = rsi.sort_values("trade_date").groupby("symbol", as_index=False).tail(1)
    latest["company_name"] = latest["symbol"].map(lambda symbol: stocks.get(symbol, {}).get("company_name") or symbol)
    return latest.sort_values("average_rsi", ascending=False).reset_index(drop=True)


@st.cache_data(ttl=300, show_spinner=False)
def get_dashboard_summary():
    ranking = get_rsi_ranking()
    return {"active_stocks": len(FileStore.active_stocks()), "latest_date": FileStore.latest_price_date(),
            "highest_rsi": ranking["average_rsi"].max() if not ranking.empty else None,
            "lowest_rsi": ranking["average_rsi"].min() if not ranking.empty else None,
            "market_average": ranking["average_rsi"].mean() if not ranking.empty else None}


@st.cache_data(ttl=300, show_spinner=False)
def get_stock_history(stock_id):
    stocks = FileStore.load_stocks()
    symbol = stocks[stock_id - 1]["symbol"]
    prices = FileStore.load_prices()
    rsi = FileStore.load_rsi()
    history = prices[prices["symbol"] == symbol].merge(rsi, on=["symbol", "trade_date"], how="left")
    return history.drop(columns=["symbol"])


@st.cache_data(ttl=300, show_spinner=False)
def get_data_status():
    prices = FileStore.load_prices()
    rsi = FileStore.load_rsi()
    coverage = prices.groupby("symbol").agg(price_count=("trade_date", "count"), earliest_date=("trade_date", "min"), latest_date=("trade_date", "max")).reset_index() if not prices.empty else pd.DataFrame()
    return {"coverage": coverage, "active_stocks": len(FileStore.active_stocks()), "inactive_stocks": len(FileStore.load_stocks()) - len(FileStore.active_stocks()), "total_prices": len(prices), "total_rsi": len(rsi), "jobs": [], "errors": []}


def refresh_data():
    st.cache_data.clear()
