from datetime import date
from typing import Dict, Any, List, Optional, Union
from sqlalchemy.orm import Session

from app.database.connection import get_db_session
from app.database.repositories import (
    StockRepository,
    DailyPriceRepository,
    DataFetchLogRepository
)
from app.services.nse_client import NSEClient
from app.services.data_normalizer import DataNormalizer
from app.services.data_validator import DataValidator
from app.utils.date_utils import parse_date, get_default_start_date, format_date_iso
from app.utils.logger import logger

class HistoricalDataService:
    """
    Service to fetch and backfill historical daily price data for NIFTY 200 stocks.
    """

    @staticmethod
    def backfill_historical_data(
        start_date: Optional[Union[str, date]] = None,
        end_date: Optional[Union[str, date]] = None,
        symbols: Optional[List[str]] = None,
        session: Optional[Session] = None
    ) -> Dict[str, Any]:
        """
        Fetches historical price data for active NIFTY 200 stocks between start_date and end_date.
        Performs normalization, validation, and bulk database UPSERT.
        """
        # Resolve dates
        parsed_start = parse_date(start_date) if start_date else get_default_start_date(years_back=1)
        parsed_end = parse_date(end_date) if end_date else date.today()

        logger.info(
            f"Starting Historical Market Data Backfill from {format_date_iso(parsed_start)} to {format_date_iso(parsed_end)}..."
        )

        summary = {
            "start_date": format_date_iso(parsed_start),
            "end_date": format_date_iso(parsed_end),
            "total_stocks": 0,
            "successful_stocks": 0,
            "failed_stocks": 0,
            "total_records_processed": 0,
            "errors": []
        }

        def _backfill_in_session(s: Session):
            # Load active stocks from DB
            active_stocks = StockRepository.get_all_active_stocks(s)
            if not active_stocks:
                err_msg = "No active stocks found in stock_master. Run universe sync first."
                logger.error(err_msg)
                summary["errors"].append({"symbol": "ALL", "error": err_msg})
                return

            if symbols:
                target_symbols = set(sym.strip().upper() for sym in symbols)
                active_stocks = [stk for stk in active_stocks if stk.symbol in target_symbols]

            summary["total_stocks"] = len(active_stocks)
            stock_id_map = {stk.symbol: stk.id for stk in active_stocks}

            logger.info(f"Targeting {len(active_stocks)} active stocks for historical backfill.")

            for idx, stock in enumerate(active_stocks, 1):
                sym = stock.symbol
                logger.info(f"[{idx}/{len(active_stocks)}] Processing historical backfill for symbol '{sym}'...")

                try:
                    # 1. Fetch raw data from NSE
                    df_raw = NSEClient.get_stock_historical_data(
                        symbol=sym,
                        start_date=parsed_start,
                        end_date=parsed_end
                    )

                    if df_raw.empty:
                        logger.warning(f"No market data returned for symbol '{sym}'.")
                        summary["failed_stocks"] += 1
                        summary["errors"].append({"symbol": sym, "error": "Empty dataset returned from NSE."})
                        continue

                    # 2. Normalize raw DataFrame
                    norm_records = DataNormalizer.normalize_price_dataframe(df_raw)
                    if not norm_records:
                        logger.warning(f"No valid normalized records created for symbol '{sym}'.")
                        summary["failed_stocks"] += 1
                        summary["errors"].append({"symbol": sym, "error": "Normalization produced 0 records."})
                        continue

                    # 3. Validate normalized records
                    valid_records, invalid_logs = DataValidator.filter_valid_price_records(
                        norm_records, stock_id_map
                    )

                    if not valid_records:
                        logger.warning(f"All records failed validation for symbol '{sym}'.")
                        summary["failed_stocks"] += 1
                        summary["errors"].append({"symbol": sym, "error": "Validation rejected all records."})
                        continue

                    # 4. Bulk UPSERT into daily_prices
                    inserted_count = DailyPriceRepository.bulk_insert_daily_prices(s, valid_records)
                    summary["total_records_processed"] += inserted_count
                    summary["successful_stocks"] += 1

                    # Log fetch attempt
                    latest_rec_date = valid_records[-1]["trade_date"]
                    DataFetchLogRepository.log_fetch_attempt(
                        session=s,
                        stock_id=stock.id,
                        trade_date=latest_rec_date,
                        fetch_status="SUCCESS",
                        source="NSELIB",
                        message=f"Successfully backfilled {inserted_count} price records."
                    )

                    logger.info(f"[OK] [{idx}/{len(active_stocks)}] '{sym}' backfill complete: {inserted_count} records upserted.")

                except Exception as e:
                    logger.error(f"[FAIL] Failed to backfill historical data for symbol '{sym}': {e}")
                    summary["failed_stocks"] += 1
                    summary["errors"].append({"symbol": sym, "error": str(e)})

                    DataFetchLogRepository.log_fetch_attempt(
                        session=s,
                        stock_id=stock.id,
                        trade_date=parsed_end,
                        fetch_status="FAILED",
                        source="NSELIB",
                        message=f"Backfill failed: {e}"
                    )

        if session is not None:
            _backfill_in_session(session)
        else:
            with get_db_session() as new_session:
                _backfill_in_session(new_session)

        logger.info(
            f"Historical Backfill Finished. Total Stocks: {summary['total_stocks']}, "
            f"Success: {summary['successful_stocks']}, Failed: {summary['failed_stocks']}, "
            f"Total Records: {summary['total_records_processed']}."
        )
        return summary
