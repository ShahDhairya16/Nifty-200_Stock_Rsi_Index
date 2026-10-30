from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional, Callable

from app.database.repositories import StockRepository, PriceRepository, RSIRepository
from app.services.data_normalizer import DataNormalizer
from app.services.historical_data_service import HistoricalDataService
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
            "history_backfill": None,
            "rsi_recomputed": False,
            "universe": None,
            "errors": [],
            "status": "SUCCESS",
        }

        latest_date = PriceRepository.latest_price_date()
        now_ist = datetime.now(ZoneInfo("Asia/Kolkata"))
        today = now_ist.date()
        # NSE's end-of-day Bhavcopy is published after the cash market closes.
        # During the session, the last complete price/RSI remains yesterday's.
        target_date = today if now_ist.time() >= datetime.strptime("16:00", "%H:%M").time() else today - timedelta(days=1)

        if latest_date is None:
            summary["status"] = "FAILED"
            summary["errors"].append("No price data in MongoDB. Run --backfill-historical first.")
            logger.error(summary["errors"][-1])
            return summary

        summary["latest_date_before"] = format_date_iso(latest_date)
        logger.info(f"DataUpdateService: Last stored price date = {latest_date}, target complete date = {target_date}")

        # Ensure the active universe and bundled snapshot match NSE. This also
        # backfills newly added constituents and recomputes their RSI.
        try:
            from app.services.universe_update_service import UniverseUpdateService

            summary["universe"] = UniverseUpdateService.auto_update(
                force=True,
                backfill_new=True,
                recompute_rsi=True,
            )
            if summary["universe"].get("errors"):
                logger.warning(
                    "DataUpdateService: Universe sync reported: "
                    f"{summary['universe']['errors']}"
                )
            if summary["universe"].get("rsi_recomputed"):
                summary["rsi_recomputed"] = True
        except Exception as exc:
            logger.warning(f"DataUpdateService: Stock universe sync skipped/failed ({exc}). Using stored active stocks.")

        # Safety net for stocks that joined the universe after the original
        # data load. They may only have the last couple of Bhavcopy rows, which
        # makes RSI 22/44/66 impossible. Backfill at least 70 recent closes.
        try:
            summary["history_backfill"] = HistoricalDataService.ensure_minimum_history()
            history_errors = (summary["history_backfill"].get("backfill") or {}).get("errors", [])
            for item in history_errors:
                message = f"{item.get('symbol')}: {item.get('error')}"
                summary["errors"].append(message)
                logger.warning(f"DataUpdateService: History backfill error — {message}")
        except Exception as exc:
            message = f"Failed to ensure minimum price history: {exc}"
            summary["errors"].append(message)
            logger.error(f"DataUpdateService: {message}")

        history_records = (
            (summary["history_backfill"] or {}).get("backfill") or {}
        ).get("total_records_processed", 0)

        # If already up-to-date (or today is weekend / market closed today)
        if latest_date >= target_date:
            if history_records > 0:
                RSIService.compute_all_active_stocks_rsi()
                summary["rsi_recomputed"] = True
            summary["status"] = "UP_TO_DATE"
            summary["latest_date_after"] = format_date_iso(latest_date)
            logger.info("DataUpdateService: Data is already up-to-date.")
            return summary

        missing_days = DataUpdateService._get_missing_trading_days(latest_date, target_date)
        summary["missing_days_checked"] = len(missing_days)

        if not missing_days:
            summary["status"] = "UP_TO_DATE"
            summary["latest_date_after"] = format_date_iso(latest_date)
            return summary

        logger.info(f"DataUpdateService: Found {len(missing_days)} missing day(s) to fetch: {missing_days}")

        # Load active symbols once
        active_stocks = StockRepository.get_active_stocks()
        active_symbols = {stock["symbol"].strip().upper() for stock in active_stocks if stock.get("symbol")}

        for index, trade_date in enumerate(missing_days, 1):
            date_str = format_date_iso(trade_date)
            try:
                try:
                    df_bhav = NSEClient.get_daily_market_data(trade_date)
                except ConnectionError as bhav_error:
                    # NSE's aggregate archive is often blocked independently
                    # of the per-symbol history endpoint. Recover the date from
                    # individual NSE histories instead of silently treating a
                    # 403 as a holiday.
                    logger.warning(f"DataUpdateService: {bhav_error} Trying per-symbol history fallback.")
                    fallback_records = []
                    for symbol in sorted(active_symbols):
                        history = NSEClient.get_stock_historical_data(symbol, trade_date, trade_date)
                        fallback_records.extend(
                            record for record in DataNormalizer.normalize_price_dataframe(history)
                            if record.get("symbol") == symbol and record.get("trade_date") == trade_date
                        )
                    if not fallback_records:
                        raise ConnectionError(f"No daily or per-symbol price data available for {date_str}.") from bhav_error
                    count = PriceRepository.bulk_upsert_prices(fallback_records)
                    summary["days_with_data"] += 1
                    summary["total_records_upserted"] += count
                    logger.info(f"DataUpdateService: Fallback upserted {count} price records for {date_str}.")
                    continue

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
        if (
            summary["days_with_data"] > 0
            or summary["total_records_upserted"] > 0
            or history_records > 0
        ):
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
        elif summary["total_records_upserted"] == 0 and summary["latest_date_after"] == summary["latest_date_before"] and latest_date < target_date:
            summary["status"] = "FAILED"
            summary["errors"].append(
                f"No new price data was stored; latest available date remains {summary['latest_date_after']}."
            )
        elif summary["total_records_upserted"] > 0:
            summary["status"] = "SUCCESS"

        logger.info(f"DataUpdateService: Done. Summary = {summary}")
        return summary
