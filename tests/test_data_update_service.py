from datetime import date, datetime as real_datetime
import unittest
from unittest.mock import patch

import pandas as pd

from app.services.data_update_service import DataUpdateService


class _BeforeCutoffDateTime(real_datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 11, 9, 10, 0, tzinfo=tz)


def _run_special_session_update(bhavcopy, upsert_count):
    from app.services import data_update_service as service_module

    with patch.object(service_module, "datetime", _BeforeCutoffDateTime), \
         patch.object(service_module.PriceRepository, "latest_price_date", side_effect=[date(2026, 11, 6), date(2026, 11, 6) if not upsert_count else date(2026, 11, 8)]), \
         patch.object(service_module.StockRepository, "get_active_stocks", return_value=[{"symbol": "RELIANCE"}]), \
         patch("app.services.universe_update_service.UniverseUpdateService.auto_update", return_value={"errors": [], "rsi_recomputed": False}), \
         patch.object(service_module.HistoricalDataService, "ensure_minimum_history", return_value={"backfill": {"total_records_processed": 0, "errors": []}}), \
         patch.object(service_module.NSEClient, "get_daily_market_data", return_value=bhavcopy), \
         patch.object(service_module.PriceRepository, "bulk_upsert_prices", return_value=upsert_count) as upsert, \
         patch.object(service_module.RSIService, "compute_all_active_stocks_rsi", return_value={"successful_stocks": 1}) as recompute:
        summary = DataUpdateService.fetch_and_update_missing_days()
    return summary, upsert, recompute


class DataUpdateServiceTests(unittest.TestCase):
    def test_weekend_special_session_is_included(self):
        self.assertEqual(DataUpdateService._get_missing_trading_days(
            date(2026, 11, 6), date(2026, 11, 8)), [date(2026, 11, 8)])

    def test_normal_weekend_has_no_missing_sessions(self):
        self.assertEqual(DataUpdateService._get_missing_trading_days(
            date(2026, 11, 13), date(2026, 11, 15)), [])

    def test_normal_weekday_is_included(self):
        self.assertEqual(DataUpdateService._get_missing_trading_days(
            date(2026, 11, 16), date(2026, 11, 17)), [date(2026, 11, 17)])

    def test_nse_holiday_is_excluded(self):
        self.assertEqual(DataUpdateService._get_missing_trading_days(
            date(2026, 11, 9), date(2026, 11, 10)), [])

    def test_empty_data_for_special_session_is_not_up_to_date(self):
        summary, upsert, _ = _run_special_session_update(pd.DataFrame(), 0)
        self.assertEqual(summary["status"], "FAILED")
        self.assertTrue(summary["errors"])
        self.assertEqual(summary["days_skipped_holiday"], 0)
        upsert.assert_not_called()

    def test_successful_special_session_is_upserted_and_rsi_recomputed(self):
        bhavcopy = pd.DataFrame([{
            "symbol": "RELIANCE", "date": "08-Nov-2026", "open": 100,
            "high": 105, "low": 99, "close": 103, "volume": 1000,
        }])
        summary, upsert, recompute = _run_special_session_update(bhavcopy, 1)
        self.assertEqual(summary["status"], "SUCCESS")
        self.assertEqual(summary["latest_date_after"], "2026-11-08")
        self.assertEqual(summary["days_with_data"], 1)
        self.assertTrue(summary["rsi_recomputed"])
        upsert.assert_called_once()
        recompute.assert_called_once()
