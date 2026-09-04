from datetime import date
from typing import Dict, Any, List, Tuple
from app.utils.logger import logger

class DataValidator:
    """
    Validates normalized market records before writing to database repositories.
    """

    @staticmethod
    def validate_price_record(record: Dict[str, Any], valid_stock_ids: Dict[str, int]) -> Tuple[bool, List[str]]:
        """
        Validates a single normalized daily price record.
        Params:
            record: Normalized dictionary (symbol, trade_date, open_price, high_price, low_price, close_price, volume)
            valid_stock_ids: Dictionary mapping stock symbol (str) -> stock_id (int)
        Returns:
            Tuple of (is_valid: bool, errors: List[str])
        """
        errors = []
        symbol = record.get("symbol")
        trade_date = record.get("trade_date")
        close_price = record.get("close_price")
        open_price = record.get("open_price")
        high_price = record.get("high_price")
        low_price = record.get("low_price")
        volume = record.get("volume")

        # 1. Symbol validation
        if not symbol or not isinstance(symbol, str):
            errors.append("Symbol is missing or invalid.")
        elif symbol not in valid_stock_ids:
            errors.append(f"Symbol '{symbol}' is not present in stock_master.")

        # 2. Trade Date validation
        if not trade_date or not isinstance(trade_date, date):
            errors.append(f"Trade date '{trade_date}' is missing or invalid.")

        # 3. Close Price validation
        if close_price is None:
            errors.append("Close price cannot be null.")
        elif close_price <= 0:
            errors.append(f"Close price must be greater than zero. Found: {close_price}")

        # 4. Open/High/Low price sanity checks
        if open_price is not None and open_price <= 0:
            errors.append(f"Open price must be greater than zero. Found: {open_price}")
        if high_price is not None and high_price <= 0:
            errors.append(f"High price must be greater than zero. Found: {high_price}")
        if low_price is not None and low_price <= 0:
            errors.append(f"Low price must be greater than zero. Found: {low_price}")

        # 5. High >= Low check
        if high_price is not None and low_price is not None:
            if high_price < low_price:
                errors.append(f"High price ({high_price}) cannot be lower than low price ({low_price}).")

        # 6. Volume check
        if volume is not None and volume < 0:
            errors.append(f"Volume cannot be negative. Found: {volume}")

        is_valid = len(errors) == 0
        return is_valid, errors

    @staticmethod
    def filter_valid_price_records(
        records: List[Dict[str, Any]],
        valid_stock_ids: Dict[str, int]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Filters a list of normalized records into valid records and invalid record logs.
        Returns:
            Tuple of (valid_records, invalid_records_info)
        """
        valid_records = []
        invalid_records = []

        for rec in records:
            is_valid, errors = DataValidator.validate_price_record(rec, valid_stock_ids)
            if is_valid:
                # Construct clean dictionary matching DailyPrice model columns
                valid_rec = {
                    "stock_id": valid_stock_ids[rec["symbol"]],
                    "trade_date": rec["trade_date"],
                    "open_price": rec.get("open_price"),
                    "high_price": rec.get("high_price"),
                    "low_price": rec.get("low_price"),
                    "close_price": rec["close_price"],
                    "volume": rec.get("volume"),
                }
                valid_records.append(valid_rec)
            else:
                symbol = rec.get("symbol", "UNKNOWN")
                t_date = rec.get("trade_date")
                logger.warning(f"Validation failed for record {symbol} ({t_date}): {', '.join(errors)}")
                invalid_records.append({
                    "record": rec,
                    "errors": errors
                })

        return valid_records, invalid_records
