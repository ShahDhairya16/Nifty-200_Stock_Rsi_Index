import streamlit as st
from frontend.components.sidebar import render_sidebar
from frontend.utils.data_loader import get_rsi_ranking
from frontend.utils.formatters import format_date

render_sidebar()
st.title("NIFTY 200 RSI Ranking")

try:
    with st.spinner("Loading RSI ranking..."):
        ranking = get_rsi_ranking()
    metric = st.selectbox("RSI Type", ["Average RSI", "RSI 22", "RSI 44", "RSI 66"])
    column = {"Average RSI": "average_rsi", "RSI 22": "rsi_22", "RSI 44": "rsi_44", "RSI 66": "rsi_66"}[metric]
    minimum, maximum = st.slider("RSI range", 0, 100, (0, 100))
    zone = st.radio("RSI Zone", ["All Stocks", "Oversold (<30)", "Weak (30-50)",
                                  "Positive (50-70)", "Strong (>70)"], horizontal=True)
    search = st.text_input("Search stock", placeholder="Symbol or company name")
    sort_label = st.selectbox("Sort by", ["Average RSI", "RSI 22", "RSI 44", "RSI 66", "Symbol"])
    direction = st.radio("Direction", ["Descending", "Ascending"], horizontal=True)

    frame = ranking.copy()
    frame = frame[frame[column].between(minimum, maximum, inclusive="both")]
    if zone != "All Stocks":
        if zone.startswith("Oversold"): frame = frame[frame[column] < 30]
        elif zone.startswith("Weak"): frame = frame[frame[column].between(30, 50, inclusive="left")]
        elif zone.startswith("Positive"): frame = frame[frame[column].between(50, 70, inclusive="left")]
        else: frame = frame[frame[column] > 70]
    if search:
        term = search.lower()
        frame = frame[frame["symbol"].str.lower().str.contains(term, na=False) |
                      frame["company_name"].str.lower().str.contains(term, na=False)]
    sort_column = {"Average RSI": "average_rsi", "RSI 22": "rsi_22", "RSI 44": "rsi_44",
                   "RSI 66": "rsi_66", "Symbol": "symbol"}[sort_label]
    frame = frame.sort_values(sort_column, ascending=direction == "Ascending", na_position="last")
    frame.insert(0, "Rank", range(1, len(frame) + 1))
    frame = frame.rename(columns={"symbol": "Symbol", "company_name": "Company Name",
                                  "trade_date": "Latest Date", "rsi_22": "RSI 22",
                                  "rsi_44": "RSI 44", "rsi_66": "RSI 66", "average_rsi": "Average RSI"})
    frame["Latest Date"] = frame["Latest Date"].map(format_date)
    st.dataframe(frame, hide_index=True, width='stretch',
                 column_config={name: st.column_config.NumberColumn(format="%.2f")
                                for name in ["RSI 22", "RSI 44", "RSI 66", "Average RSI"]})
except Exception:
    st.error("Unable to load the RSI ranking. Please verify that the database service is running.")