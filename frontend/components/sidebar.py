import streamlit as st
from frontend.utils.data_loader import get_dashboard_summary, refresh_data
from frontend.utils.formatters import format_date
from frontend.components.theme import apply_theme


def render_sidebar():
    apply_theme()
    with st.sidebar:
        st.markdown("## NIFTY 200")
        st.caption("RSI analytics workspace")
        st.divider()

        if st.button("🔄 Refresh & Update Data", width='stretch', type="primary"):
            with st.spinner("Checking for missing data…"):
                try:
                    from app.services.data_update_service import DataUpdateService
                    result = DataUpdateService.fetch_and_update_missing_days()
                except Exception as exc:
                    st.error(f"Update error: {exc}")
                    result = None

            if result is not None:
                status = result.get("status", "UNKNOWN")
                days_checked = result.get("missing_days_checked", 0)
                days_fetched = result.get("days_with_data", 0)
                records = result.get("total_records_upserted", 0)
                before = result.get("latest_date_before", "—")
                after = result.get("latest_date_after", "—")
                rsi_ok = result.get("rsi_recomputed", False)
                errors = result.get("errors", [])

                if status == "UP_TO_DATE":
                    st.success(f"✅ Data is already up-to-date ({after}).")
                elif status == "SUCCESS":
                    st.success(
                        f"✅ Updated! {days_fetched}/{days_checked} trading days fetched, "
                        f"{records:,} records added. "
                        f"RSI {'recomputed' if rsi_ok else 'unchanged'}. "
                        f"Data: {before} → {after}"
                    )
                elif status == "PARTIAL":
                    st.warning(
                        f"⚠️ Partial update: {days_fetched}/{days_checked} days, "
                        f"{records:,} records. {len(errors)} error(s)."
                    )
                    for e in errors[:3]:
                        st.caption(f"• {e}")
                else:
                    st.error(f"❌ Update failed: {'; '.join(errors[:2])}")

            refresh_data()
            st.rerun()

        try:
            summary = get_dashboard_summary()
            latest = summary.get("latest_date")
            st.caption(f"Latest data date\n{format_date(latest) if latest else 'No data yet'}")
        except Exception:
            st.caption("Latest data date\nUnavailable")