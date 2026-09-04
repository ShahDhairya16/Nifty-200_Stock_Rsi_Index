import streamlit as st
from frontend.utils.formatters import format_date, format_number


def metric_row(items):
    columns = st.columns(len(items))
    for column, (label, value) in zip(columns, items):
        column.metric(label, value)


def rsi_metric_value(value):
    return format_number(value)