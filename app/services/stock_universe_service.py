from datetime import date
import json
from pathlib import Path
from typing import Any, Dict, Optional

from app.database.repositories import StockRepository
from app.services.data_normalizer import DataNormalizer
from app.services.weekly_bollinger_service import WeeklyBollingerService
from app.utils.logger import logger


class StockUniverseService:
    """Synchronize the supplied constituent universe into MongoDB storage."""

    @staticmethod
    def apply_constituents(constituents: Any) -> Dict[str, Any]:
        """Apply a fetched constituent list to MongoDB.

        Additions are marked active, metadata changes are updated, and removed
        constituents are deactivated. Historical price/RSI records are retained.
        """
        summary = {"total_fetched": 0, "new_stocks": 0, "updated_stocks": 0, "deactivated_stocks": 0, "errors": []}
        existing = {stock["symbol"].strip().upper(): stock for stock in StockRepository.get_all_stocks()}
        fetched = {}
        rows = (
            constituents.to_dict(orient="records")
            if hasattr(constituents, "to_dict")
            else list(constituents)
        )
        for row in rows:
            stock = DataNormalizer.normalize_stock_metadata(row)
            if stock and stock.get("symbol"):
                fetched[stock["symbol"].strip().upper()] = stock
        live_count = len(fetched)

        today = date.today().isoformat()
        for symbol, stock in fetched.items():
            if symbol not in existing:
                stock["added_date"] = today
                summary["new_stocks"] += 1
            else:
                stock.update({"added_date": existing[symbol].get("added_date", today), "active": True})
                summary["updated_stocks"] += 1

        for symbol, stock in existing.items():
            if symbol not in fetched:
                stock["active"] = False
                stock["removed_date"] = today
                fetched[symbol] = stock
                summary["deactivated_stocks"] += 1

        StockRepository.bulk_upsert_stocks(sorted(fetched.values(), key=lambda item: item["symbol"]))
        summary["total_fetched"] = live_count

        # Keep historical stock, price, and RSI records for analysis. Reports
        # and current dashboards filter on active=True, so deactivated
        # constituents disappear from current rankings without losing history.
        return summary

    @staticmethod
    def sync_nifty200_universe(session: Optional[Any] = None) -> Dict[str, Any]:
        summary = {"total_fetched": 0, "new_stocks": 0, "updated_stocks": 0, "deactivated_stocks": 0, "errors": []}
        try:
            constituents = WeeklyBollingerService.fetch_stock_universe()
        except Exception as exc:
            summary["errors"].append(str(exc))
            logger.error(f"Failed to load NIFTY 750 constituents: {exc}")
            return summary

        return StockUniverseService.apply_constituents(constituents)

    @staticmethod
    def sync_bundled_nifty200_universe() -> Dict[str, Any]:
        """Sync the supplied NIFTY Total Market snapshot into MongoDB.

        Excel exports use this snapshot so their stock list matches the list
        supplied with the project, regardless of changes to the live NSE page.
        """
        summary = {
            "total_fetched": 0,
            "new_stocks": 0,
            "new_symbols": [],
            "updated_stocks": 0,
            "deactivated_stocks": 0,
            "deactivated_symbols": [],
            "errors": [],
        }
        stock_file = Path(__file__).resolve().parents[2] / "data" / "stocks.json"
        try:
            with stock_file.open("r", encoding="utf-8") as handle:
                rows = json.load(handle)
            if not isinstance(rows, list):
                raise ValueError("data/stocks.json must contain a JSON list.")
            fetched = {}
            for row in rows:
                stock = DataNormalizer.normalize_stock_metadata(row)
                if not stock:
                    raise ValueError("The bundled NIFTY 750 list contains an invalid stock row.")
                if stock["symbol"] in fetched:
                    raise ValueError(f"Duplicate symbol in bundled NIFTY 750 list: {stock['symbol']}.")
                fetched[stock["symbol"]] = stock
            if not fetched:
                raise ValueError("Expected at least one unique stock in data/stocks.json.")
        except Exception as exc:
            summary["errors"].append(str(exc))
            logger.error(f"Failed to load bundled NIFTY 750 constituents from {stock_file}: {exc}")
            return summary

        expected_symbols = set(fetched)
        existing = {stock["symbol"].strip().upper(): stock for stock in StockRepository.get_all_stocks()}
        today = date.today().isoformat()
        for symbol, stock in fetched.items():
            if symbol in existing:
                stock["added_date"] = existing[symbol].get("added_date", today)
                summary["updated_stocks"] += 1
            else:
                stock["added_date"] = today
                summary["new_stocks"] += 1
                summary["new_symbols"].append(symbol)

        for symbol, stock in existing.items():
            if symbol not in fetched:
                stock["active"] = False
                stock["removed_date"] = today
                fetched[symbol] = stock
                summary["deactivated_stocks"] += 1
                summary["deactivated_symbols"].append(symbol)

        StockRepository.bulk_upsert_stocks(sorted(fetched.values(), key=lambda item: item["symbol"]))
        summary["total_fetched"] = len(rows)

        active_symbols = {
            stock["symbol"].strip().upper()
            for stock in StockRepository.get_active_stocks()
            if stock.get("symbol")
        }
        if active_symbols != expected_symbols:
            missing = sorted(expected_symbols - active_symbols)
            unexpected = sorted(active_symbols - expected_symbols)
            summary["errors"].append(
                "MongoDB active stock universe does not match data/stocks.json. "
                f"Missing={missing}; unexpected={unexpected}."
            )
        return summary
