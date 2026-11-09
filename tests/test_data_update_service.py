from datetime import date, datetime, datetime as real_datetime, timezone
import unittest
from unittest.mock import patch

import pandas as pd

from app.services.nse_client import NSEClient
from app.services.data_update_service import DataUpdateService
from app.utils import nse_trading_calendar


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
    def setUp(self):
        # Keep unit tests deterministic and independent of NSE/network access.
        nse_trading_calendar._cached_at = datetime.now(timezone.utc)
        nse_trading_calendar._cached_holidays = set(nse_trading_calendar.NSE_HOLIDAYS)
        nse_trading_calendar._cached_special_sessions = set()

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

    def test_official_calendar_parses_holidays_and_muhurat_sessions(self):
        official_calendar = pd.DataFrame([
            {"Product": "Equities", "tradingDate": "08-Nov-2027", "description": "Diwali Laxmi Pujan*"},
            {"Product": "Equities", "tradingDate": "09-Nov-2027", "description": "Diwali Balipratipada"},
            {"Product": "Equity Derivatives", "tradingDate": "10-Nov-2027", "description": "Other segment holiday"},
        ])
        with patch.object(NSEClient, "get_trading_holiday_calendar", return_value=official_calendar):
            holidays, special_sessions = nse_trading_calendar._load_official_calendar()

        self.assertEqual(holidays, {date(2027, 11, 8), date(2027, 11, 9)})
        self.assertEqual(special_sessions, {date(2027, 11, 8)})

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
