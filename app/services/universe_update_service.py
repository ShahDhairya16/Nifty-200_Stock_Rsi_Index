import hashlib
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import config
from app.database.repositories import StockRepository, SyncMetadataRepository
from app.services.data_normalizer import DataNormalizer
from app.services.historical_data_service import HistoricalDataService
from app.services.nse_client import NSEClient
from app.services.rsi_service import RSIService
from app.services.stock_universe_service import StockUniverseService
from app.utils.logger import logger


BASE_DIR = Path(__file__).resolve().parents[2]
STOCK_SNAPSHOT_PATH = BASE_DIR / "data" / "stocks.json"


class UniverseUpdateService:
    """Keep the NIFTY 200 universe and bundled snapshot in sync with NSE.

    NSE reviews the NIFTY 200 index semi-annually (effective around the last
    trading day of March and September). Rather than assuming a fixed date,
    this service checks the official constituent file at most once per
    configured interval. Any addition or removal, whether from a scheduled
    rebalance or an ad-hoc replacement, is picked up automatically.
    """

    METADATA_KEY = "nifty200_universe"
    REBALANCE_MONTHS = (3, 9)

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")

    @staticmethod
    def _parse_timestamp(value: Any) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return None

    @classmethod
    def _last_attempt(cls, metadata: Dict[str, Any]) -> Optional[datetime]:
        candidates = [
            cls._parse_timestamp(metadata.get("last_attempt_at")),
            cls._parse_timestamp(metadata.get("last_checked_at")),
            cls._parse_timestamp(metadata.get("last_updated_at")),
        ]
        candidates = [value for value in candidates if value is not None]
        return max(candidates) if candidates else None

    @classmethod
    def _is_check_due(cls, metadata: Dict[str, Any], force: bool) -> bool:
        if force or not metadata:
            return True
        last_attempt = cls._last_attempt(metadata)
        if last_attempt is None:
            return True
        interval = max(1, int(config.UNIVERSE_CHECK_INTERVAL_HOURS))
        return (datetime.now() - last_attempt).total_seconds() >= interval * 3600

    @staticmethod
    def _symbols_hash(symbols: List[str]) -> str:
        payload = json.dumps(sorted(symbols), separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @staticmethod
    def _read_snapshot_symbols() -> Optional[set]:
        try:
            with STOCK_SNAPSHOT_PATH.open("r", encoding="utf-8") as handle:
                rows = json.load(handle)
            if not isinstance(rows, list) or not rows:
                return None
            return {
                str(row.get("symbol", "")).strip().upper()
                for row in rows
                if str(row.get("symbol", "")).strip()
            }
        except Exception:
            return None

    @staticmethod
    def _write_snapshot(constituents: List[Dict[str, Any]]) -> int:
        existing = {
            str(stock["symbol"]).strip().upper(): stock
            for stock in StockRepository.get_all_stocks()
            if stock.get("symbol")
        }
        today = date.today().isoformat()
        rows = []
        for stock in sorted(constituents, key=lambda item: item["symbol"]):
            symbol = str(stock["symbol"]).strip().upper()
            previous = existing.get(symbol, {})
            rows.append(
                {
                    "symbol": symbol,
                    "company_name": stock.get("company_name") or previous.get("company_name") or symbol,
                    "exchange": "NSE",
                    "series": stock.get("series") or previous.get("series") or "EQ",
                    "active": True,
                    "added_date": previous.get("added_date", today),
                }
            )

        if len(rows) != 200:
            raise ValueError(f"Refusing to write {len(rows)} rows to the NIFTY 200 snapshot; expected 200.")

        temporary_path = STOCK_SNAPSHOT_PATH.with_suffix(".json.tmp")
        with temporary_path.open("w", encoding="utf-8") as handle:
            json.dump(rows, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        temporary_path.replace(STOCK_SNAPSHOT_PATH)
        return len(rows)

    @classmethod
    def get_status(cls) -> Dict[str, Any]:
        metadata = SyncMetadataRepository.get(cls.METADATA_KEY) or {}
        metadata.pop("_id", None)
        return metadata

    @classmethod
    def auto_update(
        cls,
        force: bool = False,
        backfill_new: bool = True,
        recompute_rsi: bool = True,
    ) -> Dict[str, Any]:
        """Check NSE and apply any constituent changes.

        Returns a JSON-serialisable summary. Network failures are reported in
        ``errors`` instead of being raised so dashboard rendering is not broken.
        """
        metadata = SyncMetadataRepository.get(cls.METADATA_KEY) or {}
        now = cls._now()
        if not cls._is_check_due(metadata, force):
            return {
                "status": "SKIPPED",
                "checked_at": now,
                "last_checked_at": metadata.get("last_checked_at"),
                "last_updated_at": metadata.get("last_updated_at"),
                "added": [],
                "removed": [],
                "snapshot_updated": False,
                "errors": [],
            }

        try:
            constituents = NSEClient.get_nifty200_constituents()
        except Exception as exc:
            logger.warning(f"UniverseUpdateService: NSE constituent check failed: {exc}")
            cls._save_failure(metadata, now, str(exc))
            return {
                "status": "FAILED",
                "checked_at": now,
                "last_checked_at": metadata.get("last_checked_at"),
                "last_updated_at": metadata.get("last_updated_at"),
                "added": [],
                "removed": [],
                "snapshot_updated": False,
                "errors": [str(exc)],
            }

        fetched: Dict[str, Dict[str, Any]] = {}
        try:
            for row in constituents.to_dict(orient="records"):
                stock = DataNormalizer.normalize_stock_metadata(row)
                if stock and stock.get("symbol"):
                    fetched[str(stock["symbol"]).strip().upper()] = stock
        except Exception as exc:
            cls._save_failure(metadata, now, f"Invalid NSE constituent data: {exc}")
            return {
                "status": "FAILED",
                "checked_at": now,
                "added": [],
                "removed": [],
                "snapshot_updated": False,
                "errors": [f"Invalid NSE constituent data: {exc}"],
            }

        live_symbols = set(fetched)
        errors: List[str] = []
        if len(live_symbols) != 200:
            message = (
                "NSE returned an invalid NIFTY 200 list "
                f"({len(live_symbols)} unique symbols). The existing universe was kept."
            )
            logger.error(f"UniverseUpdateService: {message}")
            cls._save_failure(metadata, now, message)
            return {
                "status": "FAILED",
                "checked_at": now,
                "added": [],
                "removed": [],
                "snapshot_updated": False,
                "errors": [message],
            }

        existing_symbols = {
            str(stock["symbol"]).strip().upper()
            for stock in StockRepository.get_active_stocks()
            if stock.get("symbol")
        }
        added = sorted(live_symbols - existing_symbols)
        removed = sorted(existing_symbols - live_symbols)
        changed = bool(added or removed)

        snapshot_symbols = cls._read_snapshot_symbols()
        snapshot_changed = snapshot_symbols != live_symbols

        universe_summary = None
        if changed:
            try:
                universe_summary = StockUniverseService.apply_constituents(constituents)
                if universe_summary.get("errors"):
                    errors.extend(str(error) for error in universe_summary["errors"])
            except Exception as exc:
                message = f"Failed to apply NIFTY 200 constituents: {exc}"
                logger.error(f"UniverseUpdateService: {message}")
                errors.append(message)

        snapshot_updated = False
        if changed or snapshot_changed:
            try:
                cls._write_snapshot(list(fetched.values()))
                snapshot_updated = True
                logger.info("UniverseUpdateService: Updated data/stocks.json snapshot.")
            except Exception as exc:
                message = f"Failed to update bundled NIFTY 200 snapshot: {exc}"
                logger.error(f"UniverseUpdateService: {message}")
                errors.append(message)

        backfill_summary = None
        history_summary = None
        rsi_recomputed = False
        if added and backfill_new:
            logger.info(f"UniverseUpdateService: Backfilling newly added stocks: {added}")
            try:
                backfill_summary = HistoricalDataService.backfill_historical_data(symbols=added)
                if backfill_summary.get("errors"):
                    errors.extend(
                        f"{item.get('symbol')}: {item.get('error')}"
                        for item in backfill_summary["errors"]
                    )
            except Exception as exc:
                message = f"Failed to backfill newly added stocks: {exc}"
                logger.error(f"UniverseUpdateService: {message}")
                errors.append(message)

        if backfill_new:
            # Newly added constituents may already be marked active in MongoDB
            # without a full history (for example when they came from the
            # bundled data/stocks.json snapshot). Top up every active stock so
            # each one has enough closing prices for RSI 22/44/66.
            try:
                history_summary = HistoricalDataService.ensure_minimum_history()
                if history_summary.get("symbols_with_insufficient_history"):
                    logger.info(
                        "UniverseUpdateService: Backfilled minimum history for "
                        f"{history_summary['symbols_with_insufficient_history']} stock(s)."
                    )
                backfill = history_summary.get("backfill") or {}
                for item in backfill.get("errors", []):
                    errors.append(f"{item.get('symbol')}: {item.get('error')}")
            except Exception as exc:
                message = f"Failed to ensure minimum price history: {exc}"
                logger.error(f"UniverseUpdateService: {message}")
                errors.append(message)

        if recompute_rsi:
            added_records = (backfill_summary or {}).get("total_records_processed", 0)
            history_records = ((history_summary or {}).get("backfill") or {}).get(
                "total_records_processed", 0
            )
            if added_records or history_records:
                RSIService.compute_all_active_stocks_rsi()
                rsi_recomputed = True

        status = "UPDATED" if (changed or snapshot_updated) and not errors else (
            "PARTIAL" if (changed or snapshot_updated) else "UP_TO_DATE"
        )
        if errors and not (changed or snapshot_updated):
            status = "FAILED"

        document = {
            "last_attempt_at": now,
            "last_checked_at": now,
            "last_updated_at": now if changed else metadata.get("last_updated_at"),
            "last_change_at": now if changed else metadata.get("last_change_at"),
            "last_status": status,
            "last_error": "; ".join(errors) if errors else None,
            "symbols_hash": cls._symbols_hash(list(live_symbols)),
            "symbol_count": len(live_symbols),
            "added": added,
            "removed": removed,
            "snapshot_updated": snapshot_updated,
            "snapshot_updated_at": now if snapshot_updated else metadata.get("snapshot_updated_at"),
            "universe_summary": universe_summary,
            "backfill_summary": backfill_summary,
            "history_summary": history_summary,
            "rsi_recomputed": rsi_recomputed,
        }
        SyncMetadataRepository.save(cls.METADATA_KEY, document)
        logger.info(
            "UniverseUpdateService: check complete. "
            f"status={status}, added={added}, removed={removed}, "
            f"snapshot_updated={snapshot_updated}."
        )
        return {"status": status, "checked_at": now, "errors": errors, **document}

    @classmethod
    def _save_failure(cls, metadata: Dict[str, Any], now: str, error: str) -> None:
        document = dict(metadata)
        document.pop("_id", None)
        document.update(
            {
                "last_attempt_at": now,
                "last_status": "FAILED",
                "last_error": error,
            }
        )
        try:
            SyncMetadataRepository.save(cls.METADATA_KEY, document)
        except Exception as exc:
            logger.error(f"UniverseUpdateService: Could not persist sync metadata: {exc}")
