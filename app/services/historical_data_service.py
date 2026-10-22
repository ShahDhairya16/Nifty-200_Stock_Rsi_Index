import math
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Union

from app.database.repositories import StockRepository, PriceRepository
from app.services.data_normalizer import DataNormalizer
from app.services.nse_client import NSEClient
from app.utils.date_utils import format_date_iso, get_default_start_date, parse_date
from app.utils.logger import logger
from app.config import config


class HistoricalDataService:
    """Fetch and persist historical prices in MongoDB storage."""

    # RSI 66 needs 66 price changes, i.e. at least 67 closing prices. Keeping a
    # small buffer above that guarantees every stock can produce RSI 22/44/66
    # and an Average RSI even when it was added to the index recently.
    MIN_HISTORY_TRADING_DAYS = 70

    @staticmethod
    def history_start_date(
        end_date: Optional[Union[str, date]] = None,
        min_trading_days: int = MIN_HISTORY_TRADING_DAYS,
    ) -> date:
        """Return a calendar start date that comfortably covers ``min_trading_days``.

        NSE trades roughly five days per week, so the calendar window is widened
        to account for weekends and exchange holidays.
        """
        parsed_end = parse_date(end_date) if end_date else None
        if parsed_end is None:
            parsed_end = date.today()
        calendar_days = math.ceil(max(1, min_trading_days) * 7 / 5) + 15
        return parsed_end - timedelta(days=calendar_days)

    @staticmethod
    def _has_enough_history(
        symbol: str,
        start_date: date,
        end_date: date,
        required_days: int,
        latest_market_date: Optional[date] = None,
    ) -> bool:
        existing = PriceRepository.get_prices_for_symbol(
            symbol, start_date=start_date, end_date=end_date
        )
        if existing.empty:
            return False
        if existing["trade_date"].nunique() < required_days:
            return False

        latest_existing = existing["trade_date"].max()
        target_latest = latest_market_date or end_date
        if end_date < target_latest:
            # The requested end date is in the past and may fall on a weekend or
            # exchange holiday, so allow a week of tolerance.
            target_latest = end_date
            return latest_existing >= target_latest - timedelta(days=7)
        return latest_existing >= target_latest

    @classmethod
    def backfill_historical_data(
        cls,
        start_date: Optional[Union[str, date]] = None,
        end_date: Optional[Union[str, date]] = None,
        symbols: Optional[List[str]] = None,
        session: Optional[Any] = None,
        min_trading_days: int = MIN_HISTORY_TRADING_DAYS,
    ) -> Dict[str, Any]:
        explicit_start = parse_date(start_date) if start_date else None
        configured_start = (
            parse_date(config.HISTORICAL_START_DATE)
            if not explicit_start and config.HISTORICAL_START_DATE
            else None
        )
        configured_end = end_date or config.HISTORICAL_END_DATE or None
        parsed_end = parse_date(configured_end) if configured_end else date.today()
        if parsed_end is None:
            parsed_end = date.today()

        minimum_start = cls.history_start_date(parsed_end, min_trading_days)
        default_start = get_default_start_date(years_back=1)
        parsed_start = explicit_start or configured_start or default_start
        if not explicit_start:
            # Always fetch enough history for RSI 22/44/66, even if a stale
            # HISTORICAL_START_DATE points at a more recent date.
            parsed_start = min(parsed_start, minimum_start)

        stocks = StockRepository.get_active_stocks()
        if symbols:
            wanted = {symbol.upper() for symbol in symbols}
            stocks = [stock for stock in stocks if stock["symbol"] in wanted]

        summary = {
            "start_date": format_date_iso(parsed_start),
            "end_date": format_date_iso(parsed_end),
            "min_trading_days": min_trading_days,
            "total_stocks": len(stocks),
            "successful_stocks": 0,
            "skipped_stocks": 0,
            "failed_stocks": 0,
            "total_records_processed": 0,
            "errors": [],
        }
        valid_symbols = {stock["symbol"] for stock in stocks}
        latest_market_date = PriceRepository.latest_price_date()

        for index, stock in enumerate(stocks, 1):
            symbol = stock["symbol"]

            if cls._has_enough_history(
                symbol,
                parsed_start,
                parsed_end,
                min_trading_days,
                latest_market_date=latest_market_date,
            ):
                summary["successful_stocks"] += 1
                summary["skipped_stocks"] += 1
                continue

            try:
                raw_df = NSEClient.get_stock_historical_data(symbol, parsed_start, parsed_end)
                records = DataNormalizer.normalize_price_dataframe(raw_df)
                records = [record for record in records if record["symbol"] in valid_symbols]
                count = PriceRepository.bulk_upsert_prices(records)
                summary["successful_stocks"] += 1
                summary["total_records_processed"] += count
                logger.info(f"[OK] [{index}/{len(stocks)}] '{symbol}' saved {count} price records in MongoDB.")
            except Exception as exc:
                summary["failed_stocks"] += 1
                summary["errors"].append({"symbol": symbol, "error": str(exc)})
                logger.error(f"[FAIL] Failed to backfill '{symbol}': {exc}")

        return summary

    @classmethod
    def ensure_minimum_history(
        cls,
        min_trading_days: int = MIN_HISTORY_TRADING_DAYS,
        end_date: Optional[Union[str, date]] = None,
        symbols: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Backfill any active stock that lacks enough recent closing prices.

        This is the safety net for constituents added to the universe after the
        original data load (for example, the seven stocks added after the
        September rebalance). Without it, such stocks keep only the couple of
        rows supplied by daily Bhavcopy refreshes and never get a valid RSI 66.
        """
        target_end = parse_date(end_date) if end_date else None
        if target_end is None:
            target_end = date.today()

        stocks = StockRepository.get_active_stocks()
        if symbols:
            wanted = {symbol.strip().upper() for symbol in symbols}
            stocks = [
                stock
                for stock in stocks
                if str(stock.get("symbol", "")).strip().upper() in wanted
            ]

        start_date = cls.history_start_date(target_end, min_trading_days)
        latest_market_date = PriceRepository.latest_price_date()

        # Load the coverage window once instead of issuing one MongoDB query per
        # stock. This keeps refresh/report generation fast on remote databases.
        prices = PriceRepository.load_prices(
            start_date=start_date, end_date=target_end
        )
        if prices.empty:
            coverage = {}
        else:
            coverage = {
                row["symbol"]: (int(row["price_count"]), row["latest_date"])
                for row in (
                    prices.groupby("symbol", as_index=False)
                    .agg(
                        price_count=("trade_date", "nunique"),
                        latest_date=("trade_date", "max"),
                    )
                    .to_dict(orient="records")
                )
            }

        target_latest = latest_market_date or target_end
        if target_end < target_latest:
            target_latest = target_end
            allowed_gap = timedelta(days=7)
        else:
            allowed_gap = timedelta(0)

        insufficient: List[str] = []
        for stock in stocks:
            symbol = str(stock.get("symbol", "")).strip().upper()
            count, latest_existing = coverage.get(symbol, (0, None))
            if count < min_trading_days or latest_existing is None:
                insufficient.append(symbol)
            elif latest_existing < target_latest - allowed_gap:
                insufficient.append(symbol)

        summary = {
            "min_trading_days": min_trading_days,
            "start_date": format_date_iso(start_date),
            "end_date": format_date_iso(target_end),
            "symbols_checked": len(stocks),
            "symbols_with_insufficient_history": len(insufficient),
            "symbols": insufficient,
            "backfill": None,
        }

        if insufficient:
            logger.info(
                f"HistoricalDataService: Backfilling {len(insufficient)} stock(s) "
                f"with fewer than {min_trading_days} recent closing prices: {insufficient}"
            )
            summary["backfill"] = cls.backfill_historical_data(
                start_date=start_date,
                end_date=target_end,
                symbols=insufficient,
                min_trading_days=min_trading_days,
            )

        return summary
