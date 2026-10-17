from datetime import date
from typing import Any, Dict, List, Optional
import pandas as pd
from app.database.repositories import StockRepository, PriceRepository, RSIRepository


class FileStore:
    """
    Compatibility wrapper delegating to MongoDB repositories.
    Allows existing components to transition smoothly to MongoDB storage.
    """

    @staticmethod
    def load_stocks() -> List[Dict[str, Any]]:
        return StockRepository.get_all_stocks()

    @staticmethod
    def save_stocks(stocks: List[Dict[str, Any]]) -> None:
        StockRepository.bulk_upsert_stocks(stocks)

    @staticmethod
    def load_prices() -> pd.DataFrame:
        return PriceRepository.load_prices()

    @staticmethod
    def save_prices(prices: pd.DataFrame) -> None:
        PriceRepository.bulk_upsert_prices(prices)

    @staticmethod
    def load_rsi() -> pd.DataFrame:
        return RSIRepository.load_rsi()

    @staticmethod
    def save_rsi(rsi: pd.DataFrame) -> None:
        RSIRepository.save_rsi(rsi)

    @staticmethod
    def upsert_prices(records: List[Dict[str, Any]]) -> int:
        return PriceRepository.bulk_upsert_prices(records)

    @staticmethod
    def active_stocks() -> List[Dict[str, Any]]:
        return StockRepository.get_active_stocks()

    @staticmethod
    def latest_price_date() -> Optional[date]:
        return PriceRepository.latest_price_date()
