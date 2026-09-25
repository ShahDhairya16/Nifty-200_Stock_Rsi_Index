from datetime import date, datetime
from typing import Any, Dict, List, Optional, Union
import pandas as pd
from pymongo import ASCENDING, DESCENDING, UpdateOne

from app.database.connection import get_database
from app.utils.date_utils import format_date_iso, parse_date
from app.utils.logger import logger


class StockRepository:
    """Repository handling MongoDB operations for stock universe."""

    @staticmethod
    def get_collection():
        return get_database()["stocks"]

    @classmethod
    def get_all_stocks(cls) -> List[Dict[str, Any]]:
        """Retrieves all stocks from MongoDB sorted by symbol."""
        col = cls.get_collection()
        cursor = col.find({}, {"_id": 0}).sort("symbol", ASCENDING)
        return list(cursor)

    @classmethod
    def get_active_stocks(cls) -> List[Dict[str, Any]]:
        """Retrieves active stocks from MongoDB sorted by symbol."""
        col = cls.get_collection()
        cursor = col.find({"active": True}, {"_id": 0}).sort("symbol", ASCENDING)
        return list(cursor)

    @classmethod
    def get_stock_by_symbol(cls, symbol: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single stock by its ticker symbol."""
        col = cls.get_collection()
        return col.find_one({"symbol": symbol.strip().upper()}, {"_id": 0})

    @classmethod
    def bulk_upsert_stocks(cls, stocks: List[Dict[str, Any]]) -> int:
        """
        Upserts stock documents into the 'stocks' collection.
        Updates metadata or inserts new entries idempotently.
        """
        if not stocks:
            return 0

        col = cls.get_collection()
        operations = []
        now = datetime.now()

        for stock in stocks:
            doc = dict(stock)
            doc["symbol"] = doc["symbol"].strip().upper()
            doc["updated_at"] = now
            created_at_val = doc.pop("created_at", now)

            operations.append(
                UpdateOne(
                    {"symbol": doc["symbol"]},
                    {
                        "$set": doc,
                        "$setOnInsert": {"created_at": created_at_val},
                    },
                    upsert=True,
                )
            )

        result = col.bulk_write(operations, ordered=False)
        upserted_count = result.upserted_count + result.modified_count
        logger.info(f"Upserted/updated {upserted_count} stocks in MongoDB.")
        return upserted_count

    @classmethod
    def save_stocks(cls, stocks: List[Dict[str, Any]]) -> None:
        """Alias for bulk_upsert_stocks to maintain API compatibility."""
        cls.bulk_upsert_stocks(stocks)

    @classmethod
    def count_stocks(cls, active_only: bool = False) -> int:
        col = cls.get_collection()
        filter_query = {"active": True} if active_only else {}
        return col.count_documents(filter_query)


class PriceRepository:
    """Repository handling MongoDB operations for daily prices."""

    @staticmethod
    def get_collection():
        return get_database()["prices"]

    @classmethod
    def bulk_upsert_prices(cls, records: Union[List[Dict[str, Any]], pd.DataFrame], batch_size: int = 5000) -> int:
        """
        Bulk upserts daily price records into MongoDB using compound unique index (symbol, trade_date).
        """
        if isinstance(records, pd.DataFrame):
            if records.empty:
                return 0
            records = records.to_dict(orient="records")

        if not records:
            return 0

        col = cls.get_collection()
        total_upserted = 0
        now = datetime.now()

        for i in range(0, len(records), batch_size):
            chunk = records[i : i + batch_size]
            operations = []
            for item in chunk:
                symbol = str(item["symbol"]).strip().upper()
                raw_date = item["trade_date"]
                if isinstance(raw_date, (datetime, date)):
                    date_str = format_date_iso(raw_date)
                else:
                    parsed = parse_date(str(raw_date))
                    date_str = format_date_iso(parsed) if parsed else None

                close_price = float(item["close_price"]) if pd.notna(item.get("close_price")) else None
                if not date_str or not symbol or close_price is None:
                    continue

                doc = {
                    "symbol": symbol,
                    "trade_date": date_str,
                    "open_price": float(item["open_price"]) if pd.notna(item.get("open_price")) else None,
                    "high_price": float(item["high_price"]) if pd.notna(item.get("high_price")) else None,
                    "low_price": float(item["low_price"]) if pd.notna(item.get("low_price")) else None,
                    "close_price": close_price,
                    "volume": int(item["volume"]) if pd.notna(item.get("volume")) else None,
                    "updated_at": now,
                }

                operations.append(
                    UpdateOne(
                        {"symbol": symbol, "trade_date": date_str},
                        {"$set": doc},
                        upsert=True,
                    )
                )

            if operations:
                col.bulk_write(operations, ordered=False)
                total_upserted += len(operations)

        logger.info(f"Bulk upserted {total_upserted} price records into MongoDB.")
        return total_upserted

    @classmethod
    def upsert_prices(cls, records: List[Dict[str, Any]]) -> int:
        return cls.bulk_upsert_prices(records)

    @classmethod
    def load_prices(
        cls,
        symbol: Optional[str] = None,
        end_date: Optional[Union[str, date]] = None,
        start_date: Optional[Union[str, date]] = None,
    ) -> pd.DataFrame:
        """
        Loads daily price data from MongoDB into a pandas DataFrame.
        """
        col = cls.get_collection()
        filter_query: Dict[str, Any] = {}

        if symbol:
            filter_query["symbol"] = symbol.strip().upper()

        date_filters: Dict[str, str] = {}
        if start_date:
            parsed_start = parse_date(start_date) if not isinstance(start_date, (datetime, date)) else start_date
            date_filters["$gte"] = format_date_iso(parsed_start)
        if end_date:
            parsed_end = parse_date(end_date) if not isinstance(end_date, (datetime, date)) else end_date
            date_filters["$lte"] = format_date_iso(parsed_end)

        if date_filters:
            filter_query["trade_date"] = date_filters

        cursor = col.find(
            filter_query,
            {"_id": 0, "symbol": 1, "trade_date": 1, "open_price": 1, "high_price": 1, "low_price": 1, "close_price": 1, "volume": 1},
        ).sort([("symbol", ASCENDING), ("trade_date", ASCENDING)])

        df = pd.DataFrame(list(cursor))
        if df.empty:
            return pd.DataFrame(columns=["symbol", "trade_date", "open_price", "high_price", "low_price", "close_price", "volume"])

        df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
        return df

    @classmethod
    def get_prices_for_symbol(
        cls, symbol: str, start_date: Optional[Union[str, date]] = None, end_date: Optional[Union[str, date]] = None
    ) -> pd.DataFrame:
        return cls.load_prices(symbol=symbol, start_date=start_date, end_date=end_date)

    @classmethod
    def latest_price_date(cls) -> Optional[date]:
        """Returns the most recent trade date in the price records."""
        col = cls.get_collection()
        latest_doc = col.find_one(
            {"trade_date": {"$regex": r"^\d{4}-\d{2}-\d{2}"}},
            {"_id": 0, "trade_date": 1},
            sort=[("trade_date", DESCENDING)],
        )
        if latest_doc and latest_doc.get("trade_date"):
            return parse_date(latest_doc["trade_date"])
        return None

    @classmethod
    def get_price_coverage(cls) -> pd.DataFrame:
        """
        Calculates symbol-level price coverage directly via MongoDB aggregation pipeline.
        """
        col = cls.get_collection()
        pipeline = [
            {
                "$group": {
                    "_id": "$symbol",
                    "price_count": {"$sum": 1},
                    "earliest_date": {"$min": "$trade_date"},
                    "latest_date": {"$max": "$trade_date"},
                }
            },
            {"$project": {"_id": 0, "symbol": "$_id", "price_count": 1, "earliest_date": 1, "latest_date": 1}},
            {"$sort": {"symbol": 1}},
        ]
        results = list(col.aggregate(pipeline))
        if not results:
            return pd.DataFrame()
        df = pd.DataFrame(results)
        df["earliest_date"] = pd.to_datetime(df["earliest_date"]).dt.date
        df["latest_date"] = pd.to_datetime(df["latest_date"]).dt.date
        return df

    @classmethod
    def count_prices(cls) -> int:
        return cls.get_collection().count_documents({})


class RSIRepository:
    """Repository handling MongoDB operations for calculated RSI metrics."""

    @staticmethod
    def get_collection():
        return get_database()["rsi"]

    @classmethod
    def bulk_upsert_rsi(cls, records: Union[List[Dict[str, Any]], pd.DataFrame], batch_size: int = 5000) -> int:
        """
        Bulk upserts RSI records into MongoDB using compound unique index (symbol, trade_date).
        """
        if isinstance(records, pd.DataFrame):
            if records.empty:
                return 0
            records = records.to_dict(orient="records")

        if not records:
            return 0

        col = cls.get_collection()
        total_upserted = 0
        now = datetime.now()

        for i in range(0, len(records), batch_size):
            chunk = records[i : i + batch_size]
            operations = []
            for item in chunk:
                symbol = str(item["symbol"]).strip().upper()
                raw_date = item["trade_date"]
                if isinstance(raw_date, (datetime, date)):
                    date_str = format_date_iso(raw_date)
                else:
                    parsed = parse_date(str(raw_date))
                    date_str = format_date_iso(parsed) if parsed else None

                if not date_str or not symbol:
                    continue

                doc = {
                    "symbol": symbol,
                    "trade_date": date_str,
                    "rsi_22": float(item["rsi_22"]) if pd.notna(item.get("rsi_22")) else None,
                    "rsi_44": float(item["rsi_44"]) if pd.notna(item.get("rsi_44")) else None,
                    "rsi_66": float(item["rsi_66"]) if pd.notna(item.get("rsi_66")) else None,
                    "average_rsi": float(item["average_rsi"]) if pd.notna(item.get("average_rsi")) else None,
                    "calculation_status": item.get("calculation_status", "SUCCESS"),
                    "updated_at": now,
                }

                operations.append(
                    UpdateOne(
                        {"symbol": symbol, "trade_date": date_str},
                        {"$set": doc},
                        upsert=True,
                    )
                )

            if operations:
                col.bulk_write(operations, ordered=False)
                total_upserted += len(operations)

        logger.info(f"Bulk upserted {total_upserted} RSI records into MongoDB.")
        return total_upserted

    @classmethod
    def save_rsi(cls, rsi: pd.DataFrame) -> None:
        """Compatibility helper for saving RSI dataframe."""
        cls.bulk_upsert_rsi(rsi)

    @classmethod
    def load_rsi(
        cls,
        symbol: Optional[str] = None,
        end_date: Optional[Union[str, date]] = None,
    ) -> pd.DataFrame:
        """Loads RSI data from MongoDB into a pandas DataFrame."""
        col = cls.get_collection()
        filter_query: Dict[str, Any] = {}

        if symbol:
            filter_query["symbol"] = symbol.strip().upper()

        if end_date:
            parsed_end = parse_date(end_date) if not isinstance(end_date, (datetime, date)) else end_date
            filter_query["trade_date"] = {"$lte": format_date_iso(parsed_end)}

        cursor = col.find(
            filter_query,
            {"_id": 0, "symbol": 1, "trade_date": 1, "rsi_22": 1, "rsi_44": 1, "rsi_66": 1, "average_rsi": 1},
        ).sort([("symbol", ASCENDING), ("trade_date", ASCENDING)])

        df = pd.DataFrame(list(cursor))
        if df.empty:
            return pd.DataFrame(columns=["symbol", "trade_date", "rsi_22", "rsi_44", "rsi_66", "average_rsi"])

        df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
        return df

    @classmethod
    def get_rsi_for_symbol(cls, symbol: str) -> pd.DataFrame:
        return cls.load_rsi(symbol=symbol)

    @classmethod
    def get_latest_rsi_rankings(cls) -> pd.DataFrame:
        """
        Retrieves the latest RSI record for each active stock, combined with company names,
        sorted by average_rsi descending.
        """
        stocks = {s["symbol"]: s for s in StockRepository.get_active_stocks()}
        active_symbols = list(stocks.keys())
        if not active_symbols:
            return pd.DataFrame()

        col = cls.get_collection()
        pipeline = [
            {"$match": {"symbol": {"$in": active_symbols}}},
            {"$sort": {"trade_date": DESCENDING}},
            {
                "$group": {
                    "_id": "$symbol",
                    "trade_date": {"$first": "$trade_date"},
                    "rsi_22": {"$first": "$rsi_22"},
                    "rsi_44": {"$first": "$rsi_44"},
                    "rsi_66": {"$first": "$rsi_66"},
                    "average_rsi": {"$first": "$average_rsi"},
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "symbol": "$_id",
                    "trade_date": 1,
                    "rsi_22": 1,
                    "rsi_44": 1,
                    "rsi_66": 1,
                    "average_rsi": 1,
                }
            },
            {"$sort": {"average_rsi": DESCENDING}},
        ]

        records = list(col.aggregate(pipeline))
        if not records:
            return pd.DataFrame()

        df = pd.DataFrame(records)
        df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
        df["company_name"] = df["symbol"].map(lambda sym: stocks.get(sym, {}).get("company_name") or sym)
        return df

    @classmethod
    def count_rsi(cls) -> int:
        return cls.get_collection().count_documents({})
