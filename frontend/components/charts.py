import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from frontend.components.theme import is_dark


def chart_layout(figure, height):
    figure.update_layout(
        height=height, margin=dict(l=10, r=10, t=25, b=10),
        paper_bgcolor="#0d1b2e", plot_bgcolor="#0d1b2e",
        font=dict(color="#e8f0fb"),
        xaxis=dict(gridcolor="#1e3550"), yaxis=dict(gridcolor="#1e3550"),
    )
    return figure


def rsi_distribution(frame):
    if frame.empty:
        st.info("No RSI data is available for the distribution.")
        return
    figure = px.histogram(frame, x="average_rsi", nbins=20,
                          labels={"average_rsi": "Average RSI", "count": "Number of Stocks"},
                          color_discrete_sequence=["#2f6fed"])
    for start, end, color in [(0, 30, "#e7eefc"), (30, 50, "#f4f0df"),
                               (50, 70, "#e7f2ea"), (70, 100, "#f7e6e3")]:
        figure.add_vrect(x0=start, x1=end, fillcolor=color, opacity=0.35, line_width=0)
    chart_layout(figure, 360).update_layout(showlegend=False)
    st.plotly_chart(figure, use_container_width=True)


def price_chart(history):
    price = px.line(history, x="trade_date", y="close_price", labels={
        "trade_date": "Trade Date", "close_price": "Closing Price"})
    chart_layout(price, 360)
    st.plotly_chart(price, use_container_width=True)


def rsi_chart(history):
    figure = go.Figure()
    for column, label, color in [("rsi_22", "RSI 22", "#2f6fed"),
                                 ("rsi_44", "RSI 44", "#20a070"),
                                 ("rsi_66", "RSI 66", "#d78b27"),
                                 ("average_rsi", "Average RSI", "#c44d58")]:
        figure.add_trace(go.Scatter(x=history["trade_date"], y=history[column],
                                     mode="lines", name=label, line=dict(color=color)))
    for level in [30, 50, 70]:
        figure.add_hline(y=level, line_dash="dot", line_color="#9aa4b2")
    chart_layout(figure, 400).update_layout(yaxis=dict(range=[0, 100], title="RSI Value"),
                                            xaxis_title="Trade Date")
    st.plotly_chart(figure, use_container_width=True)