import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

st.set_page_config(page_title="NIFTY 200 RSI Dashboard", page_icon="📊",
                   layout="wide", initial_sidebar_state="expanded")


@st.cache_data(ttl=21600, show_spinner=False)
def _auto_sync_nifty200_universe():
    """Check NSE once per cache window so index changes arrive automatically."""
    try:
        from app.database.repositories import StockRepository
        from app.services.universe_update_service import UniverseUpdateService

        # A fresh database is populated explicitly from the sidebar/CLI. Do not
        # trigger a full 200-stock backfill during the first page load.
        if StockRepository.count_stocks(active_only=True) == 0:
            return {"status": "SKIPPED", "reason": "empty database"}

        return UniverseUpdateService.auto_update(
            force=False,
            backfill_new=True,
            recompute_rsi=True,
        )
    except Exception as exc:
        return {"status": "FAILED", "errors": [str(exc)]}


try:
    _auto_sync_nifty200_universe()
except Exception:
    pass

pages = [
    st.Page("pages/1_Dashboard.py", title="Dashboard", icon="📊", default=True),
    st.Page("pages/2_RSI_Ranking.py", title="RSI Ranking", icon="🏆"),
    st.Page("pages/3_Stock_Analysis.py", title="Stock Analysis", icon="📈"),
    st.Page("pages/4_AI_Advisor.py", title="AI Advisor", icon="🤖"),
    st.Page("pages/5_Reports.py", title="Reports", icon="📥"),
]
navigation = st.navigation(pages, position="sidebar", expanded=True)
navigation.run()