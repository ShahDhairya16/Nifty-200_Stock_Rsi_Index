from datetime import date
from typing import Dict, Any, List, Optional
from sqlalchemy import select, func, and_
from sqlalchemy.orm import Session

from app.database.connection import get_db_session
from app.database.models import DailyPrice, StockMaster
from app.database.repositories import StockRepository, DailyPriceRepository
from app.utils.date_utils import parse_date, is_weekend, get_date_range
from app.utils.logger import logger

class MissingDataService:
    """
    Service to detect missing trading dates and data gaps for active stocks in daily_prices.
    """

    @staticmethod
    def get_latest_database_date(session: Optional[Session] = None) -> Optional[date]:
        """
        Returns the overall latest trade date stored in daily_prices.
        """
        def _get(s: Session):
            return DailyPriceRepository.get_latest_price_date(s)

        if session:
            return _get(session)
        with get_db_session() as new_session:
            return _get(new_session)

    @staticmethod
    def detect_missing_stock_dates(
        stock_id: int,
        start_date: date,
        end_date: date,
        session: Optional[Session] = None
    ) -> List[date]:
        """
        Detects dates within start_date and end_date where the system has trading data but the specified stock lacks data.
        """
        def _detect(s: Session):
            return DailyPriceRepository.get_missing_dates(s, stock_id, start_date, end_date)

        if session:
            return _detect(session)
        with get_db_session() as new_session:
            return _detect(new_session)

    @staticmethod
    def get_missing_dates_summary(
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        session: Optional[Session] = None
    ) -> Dict[str, Any]:
        """
        Scans all active stocks and generates a summary of missing dates and coverage statistics.
        """
        def _analyze(s: Session):
            latest_db_date = MissingDataService.get_latest_database_date(s)
            target_end = end_date or date.today()
            target_start = start_date or (latest_db_date or date(2025, 1, 1))

            active_stocks = StockRepository.get_all_active_stocks(s)
            stock_gaps = {}
            total_gaps = 0

            for stock in active_stocks:
                missing = DailyPriceRepository.get_missing_dates(s, stock.id, target_start, target_end)
                # Exclude weekends from missing dates count
                missing_weekdays = [d for d in missing if not is_weekend(d)]
                if missing_weekdays:
                    stock_gaps[stock.symbol] = missing_weekdays
                    total_gaps += len(missing_weekdays)

            return {
                "latest_database_date": str(latest_db_date) if latest_db_date else None,
                "scan_start_date": str(target_start),
                "scan_end_date": str(target_end),
                "total_active_stocks": len(active_stocks),
                "stocks_with_gaps": len(stock_gaps),
                "total_missing_records": total_gaps,
                "gap_details": stock_gaps
            }

        if session:
            return _analyze(session)
        with get_db_session() as new_session:
            return _analyze(new_session)
