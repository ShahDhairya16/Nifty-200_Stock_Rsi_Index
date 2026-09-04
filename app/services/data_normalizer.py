import math
from datetime import date
from typing import Dict, Any, List, Optional
import pandas as pd

from app.utils.date_utils import parse_date
from app.utils.logger import logger

class DataNormalizer:
    """
    Normalizes varied pandas DataFrames from nselib (Bhavcopy, price_volume, constituent list)
    into standard Python dictionaries suitable for DB repositories.
    """

    # Mapping of target normalized field names to potential raw column aliases
    SYMBOL_ALIASES = ["symbol", '﻿"symbol"', "tckrsymb", "ticker"]
    SERIES_ALIASES = ["series", "sctysrs"]
    DATE_ALIASES = ["date", "traddt", "timestamp", "trade date", "trade_date"]
    OPEN_ALIASES = ["openprice", "open price", "opnpric", "open"]
    HIGH_ALIASES = ["highprice", "high price", "hghpric", "high"]
    LOW_ALIASES = ["lowprice", "low price", "lwpric", "low"]
    CLOSE_ALIASES = ["closeprice", "close price", "clspric", "close", "lastprice", "last pric"]
    VOLUME_ALIASES = ["totaltradedquantity", "ttltradgvol", "tottrdqty", "volume", "total traded quantity"]

    @staticmethod
    def _clean_key(key: Any) -> str:
        """Strips all non-ASCII-alphanumeric characters from dictionary key for robust alias matching."""
        if not key:
            return ""
        allowed = "abcdefghijklmnopqrstuvwxyz0123456789"
        return "".join(c for c in str(key).lower() if c in allowed)

    @staticmethod
    def _find_column_val(row_dict: Dict[str, Any], aliases: List[str]) -> Any:
        """Helper to retrieve value from dictionary matching any alias (alphanumeric clean)."""
        normalized_keys = {}
        for k, v in row_dict.items():
            clean_k = DataNormalizer._clean_key(k)
            if clean_k:
                normalized_keys[clean_k] = v

        for alias in aliases:
            clean_alias = DataNormalizer._clean_key(alias)
            if clean_alias in normalized_keys:
                return normalized_keys[clean_alias]
        return None

    @staticmethod
    def _clean_float(val: Any) -> Optional[float]:
        """Converts raw value to float or None if missing/invalid/NaN."""
        if val is None or pd.isna(val):
            return None
        try:
            val_str = str(val).strip().replace(",", "")
            if not val_str or val_str in ("-", "NaN", "None", "null"):
                return None
            f_val = float(val_str)
            return f_val if not math.isnan(f_val) and not math.isinf(f_val) else None
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _clean_int(val: Any) -> Optional[int]:
        """Converts raw value to int or None if missing/invalid/NaN."""
        f_val = DataNormalizer._clean_float(val)
        if f_val is None:
            return None
        return int(f_val)

    @staticmethod
    def normalize_price_row(row_dict: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Transforms a single row dictionary into normalized daily price format.
        """
        raw_symbol = DataNormalizer._find_column_val(row_dict, DataNormalizer.SYMBOL_ALIASES)
        raw_date = DataNormalizer._find_column_val(row_dict, DataNormalizer.DATE_ALIASES)
        
        if not raw_symbol or not raw_date:
            return None

        symbol = str(raw_symbol).strip().upper()
        trade_date = parse_date(raw_date)

        if not symbol or not trade_date:
            return None

        close_price = DataNormalizer._clean_float(
            DataNormalizer._find_column_val(row_dict, DataNormalizer.CLOSE_ALIASES)
        )
        if close_price is None:
            return None

        open_price = DataNormalizer._clean_float(
            DataNormalizer._find_column_val(row_dict, DataNormalizer.OPEN_ALIASES)
        )
        high_price = DataNormalizer._clean_float(
            DataNormalizer._find_column_val(row_dict, DataNormalizer.HIGH_ALIASES)
        )
        low_price = DataNormalizer._clean_float(
            DataNormalizer._find_column_val(row_dict, DataNormalizer.LOW_ALIASES)
        )
        volume = DataNormalizer._clean_int(
            DataNormalizer._find_column_val(row_dict, DataNormalizer.VOLUME_ALIASES)
        )

        return {
            "symbol": symbol,
            "trade_date": trade_date,
            "open_price": open_price,
            "high_price": high_price,
            "low_price": low_price,
            "close_price": close_price,
            "volume": volume
        }

    @staticmethod
    def normalize_price_dataframe(df: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        Converts an entire pandas DataFrame of price records into normalized dict list.
        """
        if df is None or df.empty:
            return []

        normalized_records = []
        rows = df.to_dict(orient="records")
        for r in rows:
            norm_rec = DataNormalizer.normalize_price_row(r)
            if norm_rec:
                normalized_records.append(norm_rec)
                
        return normalized_records

    @staticmethod
    def normalize_stock_metadata(row_dict: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Normalizes stock universe constituent row (symbol, company_name, exchange, series).
        """
        raw_symbol = row_dict.get("Symbol") or row_dict.get("symbol") or row_dict.get("TckrSymb")
        if not raw_symbol:
            return None

        symbol = str(raw_symbol).strip().upper()
        company_name = row_dict.get("Company Name") or row_dict.get("company_name") or row_dict.get("FinInstrmNm")
        if company_name:
            company_name = str(company_name).strip()
            
        series = row_dict.get("Series") or row_dict.get("series") or row_dict.get("SctySrs") or "EQ"
        if series:
            series = str(series).strip().upper()

        return {
            "symbol": symbol,
            "company_name": company_name,
            "exchange": "NSE",
            "series": series,
            "active": True
        }
