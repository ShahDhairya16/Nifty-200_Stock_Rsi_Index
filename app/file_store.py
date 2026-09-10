from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
STOCKS_FILE = DATA_DIR / "stocks.json"
PRICES_FILE = DATA_DIR / "prices.csv"
RSI_FILE = DATA_DIR / "rsi.csv"


class FileStore:
    """Small local-file store for the stock universe, prices, and RSI metrics."""

    @staticmethod
    def _ensure_dir() -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def load_stocks() -> List[Dict[str, Any]]:
        if not STOCKS_FILE.exists():
            return []
        return json.loads(STOCKS_FILE.read_text(encoding="utf-8"))

    @staticmethod
    def save_stocks(stocks: List[Dict[str, Any]]) -> None:
        FileStore._ensure_dir()
        STOCKS_FILE.write_text(json.dumps(stocks, indent=2, default=str), encoding="utf-8")

    @staticmethod
    def load_prices() -> pd.DataFrame:
        if not PRICES_FILE.exists():
            return pd.DataFrame(columns=["symbol", "trade_date", "open_price", "high_price", "low_price", "close_price", "volume"])
        prices = pd.read_csv(PRICES_FILE, parse_dates=["trade_date"])
        prices["trade_date"] = pd.to_datetime(prices["trade_date"]).dt.date
        return prices

    @staticmethod
    def save_prices(prices: pd.DataFrame) -> None:
        FileStore._ensure_dir()
        prices = prices.copy()
        prices["trade_date"] = pd.to_datetime(prices["trade_date"]).dt.strftime("%Y-%m-%d")
        temp_file = PRICES_FILE.with_suffix(".tmp")
        prices.sort_values(["symbol", "trade_date"]).to_csv(temp_file, index=False)
        temp_file.replace(PRICES_FILE)

    @staticmethod
    def load_rsi() -> pd.DataFrame:
        if not RSI_FILE.exists():
            return pd.DataFrame(columns=["symbol", "trade_date", "rsi_22", "rsi_44", "rsi_66", "average_rsi"])
        rsi = pd.read_csv(RSI_FILE, parse_dates=["trade_date"])
        rsi["trade_date"] = pd.to_datetime(rsi["trade_date"]).dt.date
        return rsi

    @staticmethod
    def save_rsi(rsi: pd.DataFrame) -> None:
        FileStore._ensure_dir()
        rsi = rsi.copy()
        rsi["trade_date"] = pd.to_datetime(rsi["trade_date"]).dt.strftime("%Y-%m-%d")
        temp_file = RSI_FILE.with_suffix(".tmp")
        rsi.sort_values(["symbol", "trade_date"]).to_csv(temp_file, index=False)
        temp_file.replace(RSI_FILE)

    @staticmethod
    def upsert_prices(records: List[Dict[str, Any]]) -> int:
        if not records:
            return 0
        incoming = pd.DataFrame(records)
        incoming["symbol"] = incoming["symbol"].str.upper()
        prices = FileStore.load_prices()
        prices = pd.concat([prices, incoming], ignore_index=True)
        prices = prices.drop_duplicates(["symbol", "trade_date"], keep="last")
        FileStore.save_prices(prices)
        return len(incoming)

    @staticmethod
    def active_stocks() -> List[Dict[str, Any]]:
        return [stock for stock in FileStore.load_stocks() if stock.get("active", True)]

    @staticmethod
    def latest_price_date() -> Optional[date]:
        prices = FileStore.load_prices()
        return prices["trade_date"].max() if not prices.empty else None
