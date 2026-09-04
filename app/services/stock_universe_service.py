from datetime import date
from typing import Dict, Any, List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.connection import get_db_session
from app.database.models import StockMaster
from app.services.nse_client import NSEClient
from app.services.data_normalizer import DataNormalizer
from app.utils.logger import logger

class StockUniverseService:
    """
    Service to synchronize the NIFTY 200 stock universe between NSE and stock_master DB table.
    """

    @staticmethod
    def sync_nifty200_universe(session: Optional[Session] = None) -> Dict[str, Any]:
        """
        Synchronizes stock_master with current NIFTY 200 constituents from NSE.
        Returns detailed execution summary.
        """
        logger.info("Starting NIFTY 200 Stock Universe Synchronization...")
        summary = {
            "total_fetched": 0,
            "new_stocks": 0,
            "updated_stocks": 0,
            "deactivated_stocks": 0,
            "errors": []
        }

        # 1. Fetch official NIFTY 200 constituents from NSE
        try:
            df_constituents = NSEClient.get_nifty200_constituents()
        except Exception as e:
            err_msg = f"Failed to fetch NIFTY 200 constituents from NSE: {e}"
            logger.error(err_msg)
            summary["errors"].append(err_msg)
            return summary

        if df_constituents.empty:
            err_msg = "Fetched NIFTY 200 constituent list is empty."
            logger.warning(err_msg)
            summary["errors"].append(err_msg)
            return summary

        summary["total_fetched"] = len(df_constituents)
        fetched_symbols = set()
        constituents_by_symbol = {}

        # 2. Normalize metadata
        for row in df_constituents.to_dict(orient="records"):
            norm_rec = DataNormalizer.normalize_stock_metadata(row)
            if norm_rec and norm_rec.get("symbol"):
                sym = norm_rec["symbol"]
                fetched_symbols.add(sym)
                constituents_by_symbol[sym] = norm_rec

        # 3. Synchronize with Database
        def _sync_in_session(s: Session):
            # Fetch all existing stocks
            existing_stocks = list(s.scalars(select(StockMaster)).all())
            existing_by_symbol = {stock.symbol: stock for stock in existing_stocks}

            today = date.today()

            # Process fetched constituents
            for sym, norm_data in constituents_by_symbol.items():
                if sym not in existing_by_symbol:
                    # Insert New Stock
                    new_stock = StockMaster(
                        symbol=sym,
                        company_name=norm_data.get("company_name"),
                        exchange=norm_data.get("exchange", "NSE"),
                        series=norm_data.get("series", "EQ"),
                        active=True,
                        added_date=today
                    )
                    s.add(new_stock)
                    summary["new_stocks"] += 1
                    logger.info(f"Added new stock '{sym}' to stock_master.")
                else:
                    # Update Existing Stock
                    stock = existing_by_symbol[sym]
                    is_modified = False

                    if not stock.active:
                        stock.active = True
                        stock.removed_date = None
                        is_modified = True

                    if norm_data.get("company_name") and stock.company_name != norm_data["company_name"]:
                        stock.company_name = norm_data["company_name"]
                        is_modified = True

                    if norm_data.get("series") and stock.series != norm_data["series"]:
                        stock.series = norm_data["series"]
                        is_modified = True

                    if is_modified:
                        summary["updated_stocks"] += 1
                    else:
                        summary["updated_stocks"] += 1  # Counted as retained active stock

            # Handle deactivated stocks (in DB active=True, but missing in current NIFTY 200)
            for sym, stock in existing_by_symbol.items():
                if stock.active and sym not in fetched_symbols:
                    stock.active = False
                    stock.removed_date = today
                    summary["deactivated_stocks"] += 1
                    logger.warning(f"Stock '{sym}' is no longer in NIFTY 200. Marked active=False.")

            s.flush()
            logger.info("Stock universe sync successfully flushed to database session.")

        if session is not None:
            _sync_in_session(session)
        else:
            with get_db_session() as new_session:
                _sync_in_session(new_session)

        logger.info(
            f"NIFTY 200 Universe Sync complete. "
            f"Fetched: {summary['total_fetched']}, New: {summary['new_stocks']}, "
            f"Updated/Retained: {summary['updated_stocks']}, Deactivated: {summary['deactivated_stocks']}."
        )
        return summary
