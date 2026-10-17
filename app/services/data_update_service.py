from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Callable

from app.database.repositories import StockRepository, PriceRepository, RSIRepository
from app.services.data_normalizer import DataNormalizer
from app.services.nse_client import NSEClient
from app.services.rsi_service import RSIService
from app.utils.date_utils import format_date_iso, parse_date, is_weekend
from app.utils.logger import logger


class DataUpdateService:
    """
    Detects missing trading days since the last stored price date and
    fetches NSE Bhavcopy (daily market data) for each missing day,
    bulk-upserts new prices, then recomputes RSI for all active stocks.

    Called from the dashboard sidebar Refresh button so the user never
    has to touch the CLI for daily data updates.
    """

    @staticmethod
    def _get_missing_trading_days(latest_date: date, up_to: date) -> List[date]:
        """
        Returns a list of weekday dates between (latest_date+1) and up_to inclusive.
        Weekends are skipped; NSE holidays will simply return empty Bhavcopy and be logged.
        """
        missing = []
        cursor = latest_date + timedelta(days=1)
        while cursor <= up_to:
            if not is_weekend(cursor):
                missing.append(cursor)
            cursor += timedelta(days=1)
        return missing

    @staticmethod
    def fetch_and_update_missing_days(
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> Dict[str, Any]:
        """
        Main entry point called from the dashboard refresh.
        1. Determines which trading days are missing from MongoDB.
        2. For each missing day, fetches NSE Bhavcopy and upserts NIFTY 200 prices.
        3. Recomputes RSI metrics for all active stocks.
        Returns a summary dict with counts and any errors.
        """
        summary: Dict[str, Any] = {
            "latest_date_before": None,
            "latest_date_after": None,
            "missing_days_checked": 0,
            "days_with_data": 0,
            "days_skipped_holiday": 0,
            "total_records_upserted": 0,
            "rsi_recomputed": False,
            "errors": [],
            "status": "SUCCESS",
        }

        latest_date = PriceRepository.latest_price_date()
        today = date.today()

        if latest_date is None:
            summary["status"] = "FAILED"
            summary["errors"].append("No price data in MongoDB. Run --backfill-historical first.")
            logger.error(summary["errors"][-1])
            return summary

        summary["latest_date_before"] = format_date_iso(latest_date)
        logger.info(f"DataUpdateService: Last stored price date = {latest_date}, today = {today}")

        # If already up-to-date (or today is weekend / market closed today)
        if latest_date >= today:
            summary["status"] = "UP_TO_DATE"
            summary["latest_date_after"] = format_date_iso(latest_date)
            logger.info("DataUpdateService: Data is already up-to-date.")
            return summary

        missing_days = DataUpdateService._get_missing_trading_days(latest_date, today)
        summary["missing_days_checked"] = len(missing_days)

        if not missing_days:
            summary["status"] = "UP_TO_DATE"
            summary["latest_date_after"] = format_date_iso(latest_date)
            return summary

        logger.info(f"DataUpdateService: Found {len(missing_days)} missing day(s) to fetch: {missing_days}")

        # Load active symbols once
        active_stocks = StockRepository.get_active_stocks()
        active_symbols = {stock["symbol"] for stock in active_stocks}

        for index, trade_date in enumerate(missing_days, 1):
            date_str = format_date_iso(trade_date)
            try:
                df_bhav = NSEClient.get_daily_market_data(trade_date)

                if df_bhav is None or df_bhav.empty:
                    # Likely a market holiday or trading was suspended
                    summary["days_skipped_holiday"] += 1
                    logger.info(f"DataUpdateService: No Bhavcopy data for {date_str} (holiday/weekend).")
                    continue

                # Normalise to standard OHLCV format
                records = DataNormalizer.normalize_price_dataframe(df_bhav)

                # Filter to NIFTY 200 active stocks only
                nifty200_records = [r for r in records if r.get("symbol") in active_symbols]

                if not nifty200_records:
                    summary["days_skipped_holiday"] += 1
                    logger.warning(f"DataUpdateService: Bhavcopy for {date_str} had 0 NIFTY 200 records.")
                    continue

                count = PriceRepository.bulk_upsert_prices(nifty200_records)
                summary["days_with_data"] += 1
                summary["total_records_upserted"] += count
                logger.info(f"DataUpdateService: Upserted {count} price records for {date_str}.")

            except Exception as exc:
                err_msg = f"Failed to fetch/upsert Bhavcopy for {date_str}: {exc}"
                summary["errors"].append(err_msg)
                logger.error(f"DataUpdateService: {err_msg}")
            finally:
                if progress_callback:
                    progress_callback(index, len(missing_days), date_str)

        # Always recompute RSI after any new prices land
        if summary["days_with_data"] > 0 or summary["total_records_upserted"] > 0:
            try:
                rsi_summary = RSIService.compute_all_active_stocks_rsi()
                summary["rsi_recomputed"] = True
                logger.info(
                    f"DataUpdateService: RSI recomputed — {rsi_summary['successful_stocks']} stocks updated."
                )
            except Exception as exc:
                err_msg = f"RSI recomputation failed: {exc}"
                summary["errors"].append(err_msg)
                logger.error(f"DataUpdateService: {err_msg}")

        summary["latest_date_after"] = format_date_iso(PriceRepository.latest_price_date() or latest_date)

        if summary["errors"]:
            summary["status"] = "PARTIAL" if summary["days_with_data"] > 0 else "FAILED"

        logger.info(f"DataUpdateService: Done. Summary = {summary}")
        return summary
