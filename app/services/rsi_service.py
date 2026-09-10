from typing import Any, Dict, Optional
import pandas as pd

from app.file_store import FileStore


class RSIService:
    """Calculate RSI metrics and persist them in a local CSV file."""

    @staticmethod
    def calculate_wilder_rsi(closes: pd.Series, period: int) -> pd.Series:
        if len(closes) < period + 1:
            return pd.Series(index=closes.index, dtype=float)
        delta = closes.diff()
        gain = delta.clip(lower=0.0)
        loss = -delta.clip(upper=0.0)
        avg_gain = pd.Series(index=closes.index, dtype=float)
        avg_loss = pd.Series(index=closes.index, dtype=float)
        avg_gain.iloc[period] = gain.iloc[1:period + 1].mean()
        avg_loss.iloc[period] = loss.iloc[1:period + 1].mean()
        for index in range(period + 1, len(closes)):
            avg_gain.iloc[index] = (avg_gain.iloc[index - 1] * (period - 1) + gain.iloc[index]) / period
            avg_loss.iloc[index] = (avg_loss.iloc[index - 1] * (period - 1) + loss.iloc[index]) / period
        rsi = 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
        return rsi.where(avg_loss != 0, 100.0).where(avg_gain != 0, 0.0).round(2)

    @staticmethod
    def compute_all_active_stocks_rsi(session: Optional[Any] = None, limit_days: Optional[int] = None) -> Dict[str, Any]:
        prices = FileStore.load_prices()
        stocks = FileStore.active_stocks()
        rows = []
        summary = {"total_stocks": len(stocks), "successful_stocks": 0, "failed_stocks": 0, "total_rsi_records_stored": 0, "errors": []}
        for stock in stocks:
            symbol = stock["symbol"]
            data = prices[prices["symbol"] == symbol].sort_values("trade_date").copy()
            if len(data) < 23:
                summary["failed_stocks"] += 1
                summary["errors"].append({"symbol": symbol, "reason": "Insufficient price records."})
                continue
            closes = data["close_price"].astype(float)
            data["rsi_22"] = RSIService.calculate_wilder_rsi(closes, 22)
            data["rsi_44"] = RSIService.calculate_wilder_rsi(closes, 44)
            data["rsi_66"] = RSIService.calculate_wilder_rsi(closes, 66)
            data["average_rsi"] = data[["rsi_22", "rsi_44", "rsi_66"]].mean(axis=1, skipna=False).round(2)
            calculated = data.dropna(subset=["rsi_22"])[["symbol", "trade_date", "rsi_22", "rsi_44", "rsi_66", "average_rsi"]]
            rows.append(calculated.tail(limit_days) if limit_days else calculated)
            summary["successful_stocks"] += 1
        if rows:
            new_rsi = pd.concat(rows, ignore_index=True)
            FileStore.save_rsi(new_rsi.drop_duplicates(["symbol", "trade_date"], keep="last"))
            summary["total_rsi_records_stored"] = len(new_rsi)
        return summary
