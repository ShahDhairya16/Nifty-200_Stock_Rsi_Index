from datetime import timedelta
from typing import Any, Dict, Optional
import pandas as pd

from app.database.repositories import StockRepository, PriceRepository, RSIRepository
from app.services.weekly_bollinger_service import WeeklyBollingerService


class RSIService:
    """Calculate RSI metrics and persist them in MongoDB."""

    @staticmethod
    def fetch_market_wide_closes(
        period: int = 70,
        end_date=None,
        progress_callback=None,
    ) -> Dict[str, Any]:
        """Fetch recent closes for the full active universe using parallel NSE bhavcopies.

        This shares the Bollinger service's per-session cache and bounded
        concurrent market-file fetch, avoiding one serial request per stock.
        """
        stocks = StockRepository.get_active_stocks()
        if not stocks:
            return {
                "total_stocks": 0,
                "trading_days": 0,
                "total_records_processed": 0,
                "errors": ["No active stocks are configured."],
            }

        universe = [
            {"symbol": stock["symbol"], "series": stock.get("series") or "EQ"}
            for stock in stocks
        ]
        through = WeeklyBollingerService.latest_completed_trade_date(end_date)
        dates = []
        daily_data = {}
        for fallback in range(WeeklyBollingerService.MAX_LATEST_DATE_FALLBACK_SESSIONS + 1):
            dates, daily_data = WeeklyBollingerService.fetch_daily_market_closes(
                universe,
                through,
                period,
                progress_callback=progress_callback,
            )
            newest_error = daily_data.get(dates[-1], ({}, "missing session"))[1]
            if not newest_error or fallback == WeeklyBollingerService.MAX_LATEST_DATE_FALLBACK_SESSIONS:
                break
            through = dates[-1] - timedelta(days=1)

        records = []
        close_counts = {stock["symbol"]: 0 for stock in stocks}
        errors = []
        for trade_date in dates:
            closes, error = daily_data.get(trade_date, ({}, "No market data returned"))
            if error:
                errors.append(f"{trade_date:%Y-%m-%d}: {error}")
                continue
            for symbol, close in closes.items():
                records.append({
                    "symbol": symbol,
                    "trade_date": trade_date,
                    "close_price": close,
                })
                if symbol in close_counts:
                    close_counts[symbol] += 1

        stored = PriceRepository.bulk_upsert_closes(records)
        return {
            "total_stocks": len(stocks),
            "trading_days": len(dates),
            "latest_trade_date": dates[-1] if dates else None,
            "total_records_processed": stored,
            "stocks_with_complete_closes": sum(count == period for count in close_counts.values()),
            "stocks_with_any_closes": sum(count > 0 for count in close_counts.values()),
            "stocks_missing_closes": sorted(
                symbol for symbol, count in close_counts.items() if count < period
            ),
            "errors": errors,
        }

    @staticmethod
    def calculate_wilder_rsi(closes: pd.Series, period: int) -> pd.Series:
        if len(closes) < period + 1:
            return pd.Series(index=closes.index, dtype=float)
        delta = closes.diff()
        gain = delta.clip(lower=0.0)
        loss = -delta.clip(upper=0.0)
        avg_gain = pd.Series(index=closes.index, dtype=float)
        avg_loss = pd.Series(index=closes.index, dtype=float)
        avg_gain.iloc[period] = gain.iloc[1 : period + 1].mean()
        avg_loss.iloc[period] = loss.iloc[1 : period + 1].mean()
        for index in range(period + 1, len(closes)):
            avg_gain.iloc[index] = (avg_gain.iloc[index - 1] * (period - 1) + gain.iloc[index]) / period
            avg_loss.iloc[index] = (avg_loss.iloc[index - 1] * (period - 1) + loss.iloc[index]) / period
        rsi = 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
        return rsi.where(avg_loss != 0, 100.0).where(avg_gain != 0, 0.0).round(2)

    @staticmethod
    def compute_all_active_stocks_rsi(session: Optional[Any] = None, limit_days: Optional[int] = None) -> Dict[str, Any]:
        prices = PriceRepository.load_prices()
        stocks = StockRepository.get_active_stocks()
        price_groups = {
            symbol: group.sort_values("trade_date").copy()
            for symbol, group in prices.groupby("symbol", sort=False)
        } if not prices.empty else {}
        rows = []
        summary = {"total_stocks": len(stocks), "successful_stocks": 0, "failed_stocks": 0, "total_rsi_records_stored": 0, "errors": []}

        for stock in stocks:
            symbol = stock["symbol"]
            data = price_groups.get(symbol)
            if data is None:
                data = prices.iloc[0:0].copy()
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
            RSIRepository.bulk_upsert_rsi(new_rsi.drop_duplicates(["symbol", "trade_date"], keep="last"))
            summary["total_rsi_records_stored"] = len(new_rsi)
        return summary

    @staticmethod
    def compute_recent_active_stocks_rsi(period: int = 70, force: bool = False) -> Dict[str, Any]:
        """Calculate and store RSI for the latest ``period`` market sessions only."""
        latest_date = PriceRepository.latest_price_date()
        stocks = StockRepository.get_active_stocks()
        summary = {
            "total_stocks": len(stocks),
            "successful_stocks": 0,
            "failed_stocks": 0,
            "total_rsi_records_stored": 0,
            "errors": [],
        }
        if latest_date is None or not stocks:
            return summary

        start_date = latest_date - timedelta(days=max(200, period * 3))
        prices = PriceRepository.load_prices(start_date=start_date, end_date=latest_date)
        if prices.empty:
            return summary
        dates = sorted(prices["trade_date"].unique())[-period:]
        prices = prices[prices["trade_date"].isin(dates)]
        price_groups = {
            symbol: group.sort_values("trade_date").copy()
            for symbol, group in prices.groupby("symbol", sort=False)
        }

        if not force:
            latest_rsi = RSIRepository.get_latest_rsi_rankings()
            if not latest_rsi.empty:
                latest_by_symbol = latest_rsi.set_index("symbol")
                latest_prices = prices.groupby("symbol")["trade_date"].max()
                row_counts = prices.groupby("symbol").size()
                expected = [
                    (symbol, price_date)
                    for symbol, price_date in latest_prices.items()
                    if row_counts.get(symbol, 0) >= 23
                ]
                up_to_date = bool(expected) and all(
                    symbol in latest_by_symbol.index
                    and latest_by_symbol.loc[symbol, "trade_date"] == price_date
                    and pd.notna(latest_by_symbol.loc[symbol, "rsi_22"])
                    for symbol, price_date in expected
                )
                if up_to_date:
                    summary["successful_stocks"] = len(expected)
                    summary["skipped"] = True
                    return summary

        rows = []
        for stock in stocks:
            symbol = stock["symbol"]
            data = price_groups.get(symbol)
            if data is None:
                data = prices.iloc[0:0].copy()
            if len(data) < 23:
                summary["failed_stocks"] += 1
                summary["errors"].append({"symbol": symbol, "reason": "Insufficient recent price records."})
                continue
            closes = data["close_price"].astype(float)
            data["rsi_22"] = RSIService.calculate_wilder_rsi(closes, 22)
            data["rsi_44"] = RSIService.calculate_wilder_rsi(closes, 44)
            data["rsi_66"] = RSIService.calculate_wilder_rsi(closes, 66)
            data["average_rsi"] = data[["rsi_22", "rsi_44", "rsi_66"]].mean(axis=1, skipna=False).round(2)
            calculated = data.dropna(subset=["rsi_22"])[
                ["symbol", "trade_date", "rsi_22", "rsi_44", "rsi_66", "average_rsi"]
            ]
            rows.append(calculated.tail(period))
            summary["successful_stocks"] += 1

        if rows:
            new_rsi = pd.concat(rows, ignore_index=True).drop_duplicates(
                ["symbol", "trade_date"], keep="last"
            )
            RSIRepository.bulk_upsert_rsi(new_rsi)
            summary["total_rsi_records_stored"] = len(new_rsi)
        return summary
