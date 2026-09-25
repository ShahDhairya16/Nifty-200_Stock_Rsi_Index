import streamlit as st
from frontend.utils.data_loader import get_dashboard_summary, refresh_data
from frontend.utils.formatters import format_date
from frontend.components.theme import apply_theme
from app.database.repositories import StockRepository


def _load_bundled_data():
    """Import the repository's checked-in seed files into a fresh Atlas database."""
    import json
    from pathlib import Path
    import pandas as pd

    from app.database.init_db import init_database
    from app.database.repositories import PriceRepository, RSIRepository

    root = Path(__file__).resolve().parents[2]
    data_dir = root / "data"
    if not init_database():
        raise RuntimeError("Database initialization failed")

    stocks = json.loads((data_dir / "stocks.json").read_text(encoding="utf-8"))
    prices = pd.read_csv(data_dir / "prices.csv")
    rsi = pd.read_csv(data_dir / "rsi.csv")
    stock_count = StockRepository.bulk_upsert_stocks(stocks)
    price_count = PriceRepository.bulk_upsert_prices(prices)
    rsi_count = RSIRepository.bulk_upsert_rsi(rsi)
    return stock_count, price_count, rsi_count


def render_sidebar():
    apply_theme()
    with st.sidebar:
        st.markdown("## NIFTY 200")
        st.caption("RSI analytics workspace")
        st.divider()

        try:
            if StockRepository.count_stocks() == 0:
                st.info("This database is empty. Load the bundled project data to initialize the dashboard.")
                if st.button("Initialize dashboard data", width="stretch"):
                    try:
                        with st.spinner("Importing bundled stock, price, and RSI data into MongoDB…"):
                            stocks, prices, rsi = _load_bundled_data()
                        st.success(f"Imported {stocks:,} stocks, {prices:,} prices, and {rsi:,} RSI records.")
                        refresh_data()
                        st.rerun()
                    except Exception:
                        st.error("Unable to import the bundled data. Check Atlas access and the application logs.")
        except Exception:
            pass

        if st.button("🔄 Refresh & Update Data", width='stretch', type="primary"):
            with st.spinner("Checking for missing data…"):
                try:
                    from app.services.data_update_service import DataUpdateService
                    with st.status("Checking for missing market data…", expanded=True) as status:
                        result = DataUpdateService.fetch_and_update_missing_days(
                            progress_callback=lambda done, total, day: status.update(
                                label=f"Processed {done} of {total} days through {day}"
                            )
                        )
                        status.update(label="Data update finished", state="complete")
                except Exception:
                    st.error("Unable to update market data. Check the database connection and try again.")
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
                    st.caption("Check the application logs for technical details.")
                else:
                    st.error("❌ Update failed. Check the database connection and application logs.")

            refresh_data()
            st.rerun()

        try:
            summary = get_dashboard_summary()
            latest = summary.get("latest_date")
            st.caption(f"Latest data date\n{format_date(latest) if latest else 'No data yet'}")
        except Exception:
            st.caption("Latest data date\nUnavailable")
