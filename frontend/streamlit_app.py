import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

st.set_page_config(page_title="NIFTY 200 RSI Dashboard", page_icon="📊",
                   layout="wide", initial_sidebar_state="expanded")

pages = [
    st.Page("pages/1_Dashboard.py", title="Dashboard", icon="📊", default=True),
    st.Page("pages/2_RSI_Ranking.py", title="RSI Ranking", icon="🏆"),
    st.Page("pages/3_Stock_Analysis.py", title="Stock Analysis", icon="📈"),
    st.Page("pages/5_Reports.py", title="Reports", icon="📥"),
]
navigation = st.navigation(pages, position="sidebar", expanded=True)
navigation.run()