from datetime import date
from typing import Any, Dict, List, Optional, Union

from app.file_store import FileStore
from app.services.data_normalizer import DataNormalizer
from app.services.nse_client import NSEClient
from app.utils.date_utils import format_date_iso, get_default_start_date, parse_date
from app.utils.logger import logger


class HistoricalDataService:
    """Fetch and persist historical prices in local CSV storage."""

    @staticmethod
    def backfill_historical_data(start_date: Optional[Union[str, date]] = None, end_date: Optional[Union[str, date]] = None,
                                 symbols: Optional[List[str]] = None, session: Optional[Any] = None) -> Dict[str, Any]:
        parsed_start = parse_date(start_date) if start_date else get_default_start_date(years_back=1)
        parsed_end = parse_date(end_date) if end_date else date.today()
        stocks = FileStore.active_stocks()
        if symbols:
            wanted = {symbol.upper() for symbol in symbols}
            stocks = [stock for stock in stocks if stock["symbol"] in wanted]
        summary = {"start_date": format_date_iso(parsed_start), "end_date": format_date_iso(parsed_end), "total_stocks": len(stocks), "successful_stocks": 0, "failed_stocks": 0, "total_records_processed": 0, "errors": []}
        valid_symbols = {stock["symbol"] for stock in stocks}
        existing_prices = FileStore.load_prices()
        for index, stock in enumerate(stocks, 1):
            symbol = stock["symbol"]
            existing_symbol_prices = existing_prices[existing_prices["symbol"] == symbol]
            if not existing_symbol_prices.empty and existing_symbol_prices["trade_date"].max() >= parsed_end:
                summary["successful_stocks"] += 1
                continue
            try:
                records = DataNormalizer.normalize_price_dataframe(NSEClient.get_stock_historical_data(symbol, parsed_start, parsed_end))
                records = [record for record in records if record["symbol"] in valid_symbols]
                count = FileStore.upsert_prices(records)
                summary["successful_stocks"] += 1
                summary["total_records_processed"] += count
                logger.info(f"[OK] [{index}/{len(stocks)}] '{symbol}' saved {count} price records.")
            except Exception as exc:
                summary["failed_stocks"] += 1
                summary["errors"].append({"symbol": symbol, "error": str(exc)})
                logger.error(f"[FAIL] Failed to backfill '{symbol}': {exc}")
        return summary
