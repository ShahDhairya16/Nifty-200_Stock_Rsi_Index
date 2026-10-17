import streamlit as st
from frontend.components.charts import price_chart, rsi_chart
from frontend.components.metrics import metric_row
from frontend.components.sidebar import render_sidebar
from frontend.utils.data_loader import get_rsi_ranking, get_stock_history, get_stock_list
from frontend.utils.formatters import format_date, format_number, format_price

render_sidebar()
st.title("Stock Analysis")

try:
    stocks = get_stock_list()
    active = [stock for stock in stocks if stock["active"]]
    options = {f"{stock['symbol']} — {stock['company_name']}": stock for stock in active}
    if not options:
        st.info("No active stock data is available.")
        st.stop()
    selected = st.selectbox("Select stock", list(options))
    stock = options[selected]
    with st.spinner("Loading stock analysis..."):
        history = get_stock_history(stock["id"])
    ranking = get_rsi_ranking()
    latest = history.iloc[-1] if not history.empty else None
    latest_rsi = ranking[ranking["symbol"] == stock["symbol"]].iloc[0] if not ranking[ranking["symbol"] == stock["symbol"]].empty else None
    metric_row([("Symbol", stock["symbol"]), ("Company", stock["company_name"]),
                ("Latest Close", format_price(latest["close_price"] if latest is not None else None)),
                ("RSI 22", format_number(latest_rsi["rsi_22"] if latest_rsi is not None else None)),
                ("RSI 44", format_number(latest_rsi["rsi_44"] if latest_rsi is not None else None)),
                ("RSI 66", format_number(latest_rsi["rsi_66"] if latest_rsi is not None else None)),
                ("Average RSI", format_number(latest_rsi["average_rsi"] if latest_rsi is not None else None)),
                ("Latest Date", format_date(latest["trade_date"] if latest is not None else None))])
    if history.empty:
        st.info("No historical records are available for this stock.")
    else:
        range_name = st.radio("Price history", ["Last 30 Days", "Last 70 Days", "Last 6 Months", "All Available"], horizontal=True)
        periods = {"Last 30 Days": 30, "Last 70 Days": 70, "Last 6 Months": 126}
        chart_history = history.tail(periods[range_name]) if range_name in periods else history
        st.subheader("Closing Price")
        price_chart(chart_history)
        st.subheader("RSI Trend")
        rsi_chart(chart_history)
        st.subheader("Historical Data")
        table = history.sort_values("trade_date", ascending=False).copy()
        table["trade_date"] = table["trade_date"].map(format_date)
        st.dataframe(table.rename(columns={"trade_date": "Date", "open_price": "Open", "high_price": "High",
                                           "low_price": "Low", "close_price": "Close", "volume": "Volume",
                                           "rsi_22": "RSI 22", "rsi_44": "RSI 44", "rsi_66": "RSI 66",
                                           "average_rsi": "Average RSI"}), hide_index=True, width='stretch')
except Exception:
    st.error("Unable to load stock analysis. Check the MongoDB settings in Streamlit Secrets or your local .env, then try again.")
