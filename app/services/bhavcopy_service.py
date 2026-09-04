from datetime import date
from typing import Dict, Any, Optional, Union
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
from app.utils.date_utils import parse_date, format_date_iso
from app.utils.logger import logger

class BhavcopyService:
    """
    Service to fetch daily NSE Bhavcopy and efficiently ingest price updates for all NIFTY 200 stocks.
    """

    @staticmethod
    def fetch_daily_bhavcopy(
        trade_date: Union[str, date],
        session: Optional[Session] = None
    ) -> Dict[str, Any]:
        """
        Fetches full NSE market Bhavcopy for a given trade date and updates daily_prices for NIFTY 200 stocks.
        """
        parsed_date = parse_date(trade_date)
        if not parsed_date:
            raise ValueError(f"Invalid trade_date specified: {trade_date}")

        date_iso = format_date_iso(parsed_date)
        logger.info(f"Processing NSE Bhavcopy ingestion for date {date_iso}...")

        summary = {
            "trade_date": date_iso,
            "total_bhavcopy_rows": 0,
            "nifty200_records_found": 0,
            "records_upserted": 0,
            "status": "SUCCESS",
            "error": None
        }

        def _bhavcopy_in_session(s: Session):
            # Load active stocks from DB
            active_stocks = StockRepository.get_all_active_stocks(s)
            if not active_stocks:
                summary["status"] = "FAILED"
                summary["error"] = "No active stocks found in stock_master."
                logger.error(summary["error"])
                return

            stock_id_map = {stk.symbol: stk.id for stk in active_stocks}

            # 1. Fetch Bhavcopy from NSE
            df_bhav = NSEClient.get_daily_market_data(parsed_date)
            if df_bhav.empty:
                summary["status"] = "SKIPPED"
                summary["error"] = f"No Bhavcopy available for date {date_iso} (market closed / holiday)."
                logger.info(summary["error"])
                return

            summary["total_bhavcopy_rows"] = len(df_bhav)

            # 2. Normalize full market records
            norm_records = DataNormalizer.normalize_price_dataframe(df_bhav)

            # 3. Filter only for NIFTY 200 active symbols
            nifty200_records = [rec for rec in norm_records if rec.get("symbol") in stock_id_map]
            summary["nifty200_records_found"] = len(nifty200_records)

            if not nifty200_records:
                summary["status"] = "SKIPPED"
                summary["error"] = f"No NIFTY 200 constituent records found in Bhavcopy for {date_iso}."
                logger.warning(summary["error"])
                return

            # 4. Validate records
            valid_records, invalid_logs = DataValidator.filter_valid_price_records(
                nifty200_records, stock_id_map
            )

            if not valid_records:
                summary["status"] = "FAILED"
                summary["error"] = f"All NIFTY 200 records failed validation for {date_iso}."
                logger.error(summary["error"])
                return

            # 5. Bulk UPSERT
            upserted = DailyPriceRepository.bulk_insert_daily_prices(s, valid_records)
            summary["records_upserted"] = upserted

            # Log fetch attempt
            for stk_sym, stk_id in stock_id_map.items():
                if any(r["symbol"] == stk_sym for r in valid_records):
                    DataFetchLogRepository.log_fetch_attempt(
                        session=s,
                        stock_id=stk_id,
                        trade_date=parsed_date,
                        fetch_status="SUCCESS",
                        source="NSE_BHAVCOPY",
                        message=f"Ingested daily Bhavcopy record for {date_iso}."
                    )

            logger.info(f"Bhavcopy ingestion successful for {date_iso}: {upserted} records updated.")

        if session is not None:
            _bhavcopy_in_session(session)
        else:
            with get_db_session() as new_session:
                _bhavcopy_in_session(new_session)

        return summary
