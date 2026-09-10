from datetime import date
from typing import Any, Dict, Optional

from app.file_store import FileStore
from app.services.data_normalizer import DataNormalizer
from app.services.nse_client import NSEClient
from app.utils.logger import logger


class StockUniverseService:
    """Synchronize the NIFTY 200 universe into local JSON storage."""

    @staticmethod
    def sync_nifty200_universe(session: Optional[Any] = None) -> Dict[str, Any]:
        summary = {"total_fetched": 0, "new_stocks": 0, "updated_stocks": 0, "deactivated_stocks": 0, "errors": []}
        try:
            constituents = NSEClient.get_nifty200_constituents()
        except Exception as exc:
            summary["errors"].append(str(exc))
            logger.error(f"Failed to fetch NIFTY 200 constituents: {exc}")
            return summary
        existing = {stock["symbol"]: stock for stock in FileStore.load_stocks()}
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
        FileStore.save_stocks(sorted(fetched.values(), key=lambda item: item["symbol"]))
        summary["total_fetched"] = len(constituents)
        return summary
