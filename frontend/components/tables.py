import pandas as pd
import streamlit as st
from frontend.utils.formatters import format_date


def ranking_table(frame, limit=None):
    view = frame.head(limit).copy() if limit else frame.copy()
    if view.empty:
        st.info("No RSI records are available.")
        return
    view.insert(0, "Rank", range(1, len(view) + 1))
    view = view.rename(columns={"symbol": "Symbol", "company_name": "Company",
                                "trade_date": "Latest Date", "rsi_22": "RSI 22",
                                "rsi_44": "RSI 44", "rsi_66": "RSI 66",
                                "average_rsi": "Average RSI"})
    if "Latest Date" in view:
        view["Latest Date"] = view["Latest Date"].map(format_date)
    st.dataframe(view, hide_index=True, width='stretch',
                 column_config={column: st.column_config.NumberColumn(format="%.2f")
                                for column in ["RSI 22", "RSI 44", "RSI 66", "Average RSI"]
                                if column in view})