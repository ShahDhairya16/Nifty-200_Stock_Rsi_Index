from datetime import date
import json
from pathlib import Path
from typing import Any, Dict, Optional

from app.database.repositories import StockRepository
from app.services.data_normalizer import DataNormalizer
from app.services.nse_client import NSEClient
from app.utils.logger import logger


class StockUniverseService:
    """Synchronize the NIFTY 200 universe into MongoDB storage."""

    @staticmethod
    def sync_nifty200_universe(session: Optional[Any] = None) -> Dict[str, Any]:
        summary = {"total_fetched": 0, "new_stocks": 0, "updated_stocks": 0, "deactivated_stocks": 0, "errors": []}
        try:
            constituents = NSEClient.get_nifty200_constituents()
        except Exception as exc:
            summary["errors"].append(str(exc))
            logger.error(f"Failed to fetch NIFTY 200 constituents: {exc}")
            return summary

        existing = {stock["symbol"]: stock for stock in StockRepository.get_all_stocks()}
        fetched = {}
        for row in constituents.to_dict(orient="records"):
            stock = DataNormalizer.normalize_stock_metadata(row)
            if stock and stock.get("symbol"):
                fetched[stock["symbol"]] = stock

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
        summary["total_fetched"] = len(constituents)

        # Keep historical stock, price, and RSI records for analysis. Reports
        # and current dashboards filter on active=True, so deactivated
        # constituents disappear from current rankings without losing history.
        return summary

    @staticmethod
    def sync_bundled_nifty200_universe() -> Dict[str, Any]:
        """Sync the repository's pinned constituent snapshot into MongoDB.

        Excel exports use this snapshot so their stock list matches the list
        supplied with the project, regardless of changes to the live NSE page.
        """
        summary = {"total_fetched": 0, "new_stocks": 0, "updated_stocks": 0, "deactivated_stocks": 0, "errors": []}
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
                    raise ValueError("The bundled NIFTY 200 list contains an invalid stock row.")
                if stock["symbol"] in fetched:
                    raise ValueError(f"Duplicate symbol in bundled NIFTY 200 list: {stock['symbol']}.")
                fetched[stock["symbol"]] = stock
            if len(fetched) != 200:
                raise ValueError(f"Expected exactly 200 unique stocks in data/stocks.json; found {len(fetched)}.")
        except Exception as exc:
            summary["errors"].append(str(exc))
            logger.error(f"Failed to load bundled NIFTY 200 constituents from {stock_file}: {exc}")
            return summary

        existing = {stock["symbol"].strip().upper(): stock for stock in StockRepository.get_all_stocks()}
        today = date.today().isoformat()
        for symbol, stock in fetched.items():
            if symbol in existing:
                stock["added_date"] = existing[symbol].get("added_date", today)
                summary["updated_stocks"] += 1
            else:
                stock["added_date"] = today
                summary["new_stocks"] += 1

        for symbol, stock in existing.items():
            if symbol not in fetched:
                stock["active"] = False
                stock["removed_date"] = today
                fetched[symbol] = stock
                summary["deactivated_stocks"] += 1

        StockRepository.bulk_upsert_stocks(sorted(fetched.values(), key=lambda item: item["symbol"]))
        summary["total_fetched"] = len(rows)
        return summary
