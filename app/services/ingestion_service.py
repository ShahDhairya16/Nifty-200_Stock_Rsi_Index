from typing import Any, Dict, List, Optional, Union
from datetime import date

from app.services.historical_data_service import HistoricalDataService
from app.services.rsi_service import RSIService
from app.services.stock_universe_service import StockUniverseService


class IngestionService:
    """Orchestrate NSE ingestion using local files only."""

    @staticmethod
    def sync_stock_universe() -> Dict[str, Any]:
        return StockUniverseService.sync_nifty200_universe()

    @staticmethod
    def backfill_historical_data(start_date: Optional[Union[str, date]] = None, end_date: Optional[Union[str, date]] = None,
                                 symbols: Optional[List[str]] = None) -> Dict[str, Any]:
        return HistoricalDataService.backfill_historical_data(start_date, end_date, symbols)

    @staticmethod
    def update_missing_market_data(start_date: Optional[Union[str, date]] = None, end_date: Optional[Union[str, date]] = None) -> Dict[str, Any]:
        return HistoricalDataService.backfill_historical_data(start_date, end_date)
