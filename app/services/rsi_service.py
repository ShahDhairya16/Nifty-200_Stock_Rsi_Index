from datetime import date
from typing import Dict, Any, List, Optional, Tuple
import pandas as pd
import numpy as np
from sqlalchemy.orm import Session

from app.database.connection import get_db_session
from app.database.models import DailyPrice, StockMaster
from app.database.repositories import (
    StockRepository,
    DailyPriceRepository,
    RSIMetricsRepository
)
from app.utils.logger import logger

class RSIService:
    """
    Service to calculate Wilder's RSI (periods 22, 44, 66, and Average RSI) and store metrics in MySQL.
    """

    @staticmethod
    def calculate_wilder_rsi(closes: pd.Series, period: int) -> pd.Series:
        """
        Calculates Wilder's Smoothed RSI for a given period N.
        Params:
            closes: pandas Series of closing prices ordered by date ascending.
            period: RSI period (e.g. 22, 44, 66)
        Returns:
            pandas Series of RSI values matching the index of closes.
        """
        if len(closes) < period + 1:
            return pd.Series(index=closes.index, dtype=float)

        delta = closes.diff()
        gain = delta.clip(lower=0.0)
        loss = -1.0 * delta.clip(upper=0.0)

        avg_gain = pd.Series(index=closes.index, dtype=float)
        avg_loss = pd.Series(index=closes.index, dtype=float)

        # First average gain & loss over period N (at index = period)
        avg_gain.iloc[period] = gain.iloc[1:period + 1].mean()
        avg_loss.iloc[period] = loss.iloc[1:period + 1].mean()

        # Exponential Wilder smoothing for i > period
        for i in range(period + 1, len(closes)):
            avg_gain.iloc[i] = (avg_gain.iloc[i - 1] * (period - 1) + gain.iloc[i]) / period
            avg_loss.iloc[i] = (avg_loss.iloc[i - 1] * (period - 1) + loss.iloc[i]) / period

        rs = avg_gain / avg_loss
        
        # Handle zero loss (RS = infinity -> RSI = 100)
        rsi = 100.0 - (100.0 / (1.0 + rs))
        rsi = rsi.where(avg_loss != 0, 100.0)
        rsi = rsi.where(avg_gain != 0, 0.0)
        
        return rsi.round(4)

    @staticmethod
    def compute_and_store_rsi_for_stock(
        session: Session,
        stock_id: int,
        limit_days: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Fetches price history from DB for stock_id, calculates RSI 22, 44, 66 & Average RSI,
        and upserts records into stock_rsi_metrics table.
        """
        # Fetch prices ordered by date ascending
        price_records = DailyPriceRepository.get_prices_by_stock(session, stock_id)
        if not price_records:
            return {"stock_id": stock_id, "processed": 0, "status": "FAILED", "reason": "No price records found."}

        if len(price_records) < 23:  # Minimum 22+1 required for RSI 22
            return {
                "stock_id": stock_id,
                "processed": 0,
                "status": "SKIPPED",
                "reason": f"Insufficient price records ({len(price_records)} available, minimum 23 required)."
            }

        # Convert to DataFrame
        data = [{
            "trade_date": p.trade_date,
            "close_price": float(p.close_price)
        } for p in price_records]
        
        df = pd.DataFrame(data).sort_values("trade_date").reset_index(drop=True)

        # Calculate RSI 22, 44, 66
        df["rsi_22"] = RSIService.calculate_wilder_rsi(df["close_price"], 22)
        df["rsi_44"] = RSIService.calculate_wilder_rsi(df["close_price"], 44)
        df["rsi_66"] = RSIService.calculate_wilder_rsi(df["close_price"], 66)

        # Calculate Average RSI = (RSI22 + RSI44 + RSI66) / 3
        df["average_rsi"] = df[["rsi_22", "rsi_44", "rsi_66"]].mean(axis=1, skipna=False).round(4)

        # Filter rows where at least RSI 22 is calculated
        calculated_df = df.dropna(subset=["rsi_22"])

        if limit_days and len(calculated_df) > limit_days:
            calculated_df = calculated_df.iloc[-limit_days:]

        rsi_records = []
        for _, row in calculated_df.iterrows():
            rsi_records.append({
                "stock_id": stock_id,
                "trade_date": row["trade_date"],
                "rsi_22": None if pd.isna(row["rsi_22"]) else float(row["rsi_22"]),
                "rsi_44": None if pd.isna(row["rsi_44"]) else float(row["rsi_44"]),
                "rsi_66": None if pd.isna(row["rsi_66"]) else float(row["rsi_66"]),
                "average_rsi": None if pd.isna(row["average_rsi"]) else float(row["average_rsi"]),
                "calculation_status": "SUCCESS"
            })

        upserted_count = RSIMetricsRepository.bulk_insert_rsi_metrics(session, rsi_records)
        return {
            "stock_id": stock_id,
            "processed": len(rsi_records),
            "upserted": upserted_count,
            "status": "SUCCESS"
        }

    @staticmethod
    def compute_all_active_stocks_rsi(
        session: Optional[Session] = None,
        limit_days: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Calculates and stores RSI metrics across all active NIFTY 200 stocks.
        """
        summary = {
            "total_stocks": 0,
            "successful_stocks": 0,
            "failed_stocks": 0,
            "total_rsi_records_stored": 0,
            "errors": []
        }

        def _compute_in_session(s: Session):
            active_stocks = StockRepository.get_all_active_stocks(s)
            summary["total_stocks"] = len(active_stocks)

            for idx, stock in enumerate(active_stocks, 1):
                try:
                    res = RSIService.compute_and_store_rsi_for_stock(s, stock.id, limit_days)
                    if res["status"] == "SUCCESS":
                        summary["successful_stocks"] += 1
                        summary["total_rsi_records_stored"] += res.get("upserted", 0)
                        logger.info(f"[{idx}/{len(active_stocks)}] RSI calculated for '{stock.symbol}': {res.get('processed')} records.")
                    else:
                        summary["failed_stocks"] += 1
                        summary["errors"].append({"symbol": stock.symbol, "reason": res.get("reason")})
                        logger.warning(f"[{idx}/{len(active_stocks)}] RSI skipped/failed for '{stock.symbol}': {res.get('reason')}")
                except Exception as e:
                    summary["failed_stocks"] += 1
                    summary["errors"].append({"symbol": stock.symbol, "reason": str(e)})
                    logger.error(f"[{idx}/{len(active_stocks)}] Failed RSI computation for '{stock.symbol}': {e}")

        if session:
            _compute_in_session(session)
        else:
            with get_db_session() as new_session:
                _compute_in_session(new_session)

        return summary
