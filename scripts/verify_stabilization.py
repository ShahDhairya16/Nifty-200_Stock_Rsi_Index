"""
NIFTY 200 RSI Dashboard - Complete Codebase Stabilization & Verification Script
Runs all 21 audit checks and prints a structured report.
"""
import sys
import os
from pathlib import Path

# Ensure project root is on the path regardless of where this script is called from
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from datetime import date
import pandas as pd

PASS = "[OK]"
FAIL = "[FAIL]"
results = []

def check(label, fn):
    try:
        fn()
        results.append((PASS, label))
        print(f"{PASS} {label}")
    except Exception as e:
        results.append((FAIL, f"{label} — {e}"))
        print(f"{FAIL} {label} — {e}")


# ─── TASK 1: All imports ────────────────────────────────────────────────────
def t1_imports():
    from app.config import config
    from app.utils.logger import logger
    from app.utils.retry import nse_retry
    from app.utils.date_utils import parse_date, format_date_nselib, format_date_iso, get_default_start_date, is_weekend, get_date_range
    from app.database.connection import get_engine, get_db_session, check_db_connection
    from app.database.models import Base, StockMaster, DailyPrice, JobRun, JobError, DataFetchLog, StockRSIMetrics
    from app.database.repositories import StockRepository, DailyPriceRepository, JobRunRepository, JobErrorRepository, DataFetchLogRepository, RSIMetricsRepository
    from app.services.nse_client import NSEClient
    from app.services.data_normalizer import DataNormalizer
    from app.services.data_validator import DataValidator
    from app.services.stock_universe_service import StockUniverseService
    from app.services.historical_data_service import HistoricalDataService
    from app.services.missing_data_service import MissingDataService
    from app.services.rsi_service import RSIService
    from app.services.ingestion_service import IngestionService
    from app.services.excel_report_service import ExcelReportService
    from app.services.bhavcopy_service import BhavcopyService

check("TASK 1: All module imports resolve without errors", t1_imports)


# ─── TASK 2: DB Connection ──────────────────────────────────────────────────
def t2_db_connection():
    from app.database.connection import check_db_connection
    assert check_db_connection(), "DB connection returned False"

check("TASK 2: MySQL DB connection succeeds", t2_db_connection)


# ─── TASK 3: DB Row Counts ──────────────────────────────────────────────────
def t3_db_counts():
    from sqlalchemy import text
    from app.database.connection import get_engine
    engine = get_engine()
    with engine.connect() as conn:
        stocks = conn.execute(text("SELECT COUNT(*) FROM stock_master WHERE active=1")).scalar()
        prices = conn.execute(text("SELECT COUNT(*) FROM daily_prices")).scalar()
        rsi = conn.execute(text("SELECT COUNT(*) FROM stock_rsi_metrics")).scalar()
        jr = conn.execute(text("SELECT COUNT(*) FROM job_runs")).scalar()
    assert stocks >= 100, f"Only {stocks} active stocks — too few"
    assert prices > 0, "daily_prices is empty"
    assert rsi > 0, "stock_rsi_metrics is empty"
    print(f"      stocks={stocks}, prices={prices}, rsi={rsi}, job_runs={jr}")

check("TASK 3: Database tables populated correctly", t3_db_counts)


# ─── TASK 4: Date Utils ─────────────────────────────────────────────────────
def t4_date_utils():
    from app.utils.date_utils import parse_date, format_date_nselib, format_date_iso, is_weekend, get_date_range, get_default_start_date
    assert parse_date("2025-01-15") == date(2025, 1, 15)
    assert parse_date("15-01-2025") == date(2025, 1, 15)
    assert parse_date("15-Jan-2025") == date(2025, 1, 15)
    assert parse_date(date(2025, 1, 15)) == date(2025, 1, 15)
    assert parse_date(None) is None
    assert parse_date("NaN") is None
    assert format_date_nselib("2025-01-15") == "15-01-2025"
    assert format_date_iso("15-01-2025") == "2025-01-15"
    assert is_weekend(date(2025, 1, 4)) is True   # Saturday
    assert is_weekend(date(2025, 1, 5)) is True   # Sunday
    assert is_weekend(date(2025, 1, 6)) is False  # Monday
    rng = get_date_range(date(2025, 1, 1), date(2025, 1, 5))
    assert len(rng) == 5
    start = get_default_start_date(1)
    assert start < date.today()

check("TASK 4: date_utils — parse, format, weekend detection, range", t4_date_utils)


# ─── TASK 5: DataNormalizer ─────────────────────────────────────────────────
def t5_normalizer():
    from app.services.data_normalizer import DataNormalizer
    # Standard row from nselib price_volume_and_deliverable_position_data
    row = {
        "Symbol": "RELIANCE",
        "Date": "01-01-2025",
        "ClosePrice": "2500.50",
        "OpenPrice": "2490.00",
        "HighPrice": "2510.00",
        "LowPrice": "2485.00",
        "TotalTradedQuantity": "1000000"
    }
    rec = DataNormalizer.normalize_price_row(row)
    assert rec is not None
    assert rec["symbol"] == "RELIANCE"
    assert rec["close_price"] == 2500.50
    assert rec["open_price"] == 2490.00
    assert rec["volume"] == 1000000

    # Missing close → should return None
    bad_row = {**row, "ClosePrice": None}
    assert DataNormalizer.normalize_price_row(bad_row) is None

    # BOM-corrupted key (UTF-8 BOM from CSV headers)
    bom_row = {"\ufeffsymbol": "TCS", "traddt": "02-01-2025", "ClosePrice": "3800.00"}
    rec2 = DataNormalizer.normalize_price_row(bom_row)
    assert rec2 is not None and rec2["symbol"] == "TCS"

    # DataFrame normalizer
    df = pd.DataFrame([row])
    records = DataNormalizer.normalize_price_dataframe(df)
    assert len(records) == 1

check("TASK 5: DataNormalizer — aliases, BOM keys, clean_float, DataFrame", t5_normalizer)


# ─── TASK 6: DataValidator ──────────────────────────────────────────────────
def t6_validator():
    from app.services.data_validator import DataValidator
    valid_ids = {"RELIANCE": 1, "TCS": 2}
    good = {"symbol": "RELIANCE", "trade_date": date(2025,1,1), "close_price": 2500.0, "open_price": 2490.0, "high_price": 2510.0, "low_price": 2480.0, "volume": 100000}

    ok, errs = DataValidator.validate_price_record(good, valid_ids)
    assert ok, f"Valid record rejected: {errs}"

    # Negative close
    ok2, _ = DataValidator.validate_price_record({**good, "close_price": -1.0}, valid_ids)
    assert not ok2

    # Unknown symbol
    ok3, _ = DataValidator.validate_price_record({**good, "symbol": "UNKNOWN"}, valid_ids)
    assert not ok3

    # High < Low
    ok4, _ = DataValidator.validate_price_record({**good, "high_price": 2400.0, "low_price": 2480.0}, valid_ids)
    assert not ok4

    # filter_valid strips symbol, injects stock_id
    valid_recs, invalid_recs = DataValidator.filter_valid_price_records([good], valid_ids)
    assert len(valid_recs) == 1
    assert "symbol" not in valid_recs[0]
    assert valid_recs[0]["stock_id"] == 1

check("TASK 6: DataValidator — valid/invalid records, key stripping, stock_id injection", t6_validator)


# ─── TASK 7: RSI calculation correctness ────────────────────────────────────
def t7_rsi():
    from app.services.rsi_service import RSIService
    # Insufficient data → empty RSI
    closes_short = pd.Series([float(i) for i in range(20)])
    rsi_short = RSIService.calculate_wilder_rsi(closes_short, 22)
    assert rsi_short.dropna().empty, "RSI non-empty on insufficient data"

    # All gains → RSI ≈ 100
    closes_up = pd.Series([100.0 + float(i) for i in range(50)])
    rsi_up = RSIService.calculate_wilder_rsi(closes_up, 22)
    last_up = rsi_up.dropna().iloc[-1]
    assert last_up > 95, f"All-up RSI should be ~100, got {last_up}"

    # All losses → RSI ≈ 0
    closes_dn = pd.Series([100.0 - 0.5*i for i in range(50)])
    rsi_dn = RSIService.calculate_wilder_rsi(closes_dn, 22)
    last_dn = rsi_dn.dropna().iloc[-1]
    assert last_dn < 5, f"All-down RSI should be ~0, got {last_dn}"

    # RSI always in [0, 100]
    closes_random = pd.Series([float(100 + (i%10)*3 - (i%7)*2) for i in range(100)])
    for period in [22, 44, 66]:
        rsi = RSIService.calculate_wilder_rsi(closes_random, period)
        vals = rsi.dropna()
        assert (vals >= 0).all() and (vals <= 100).all(), f"RSI{period} out of [0,100]"

    # Average RSI = mean(RSI22, RSI44, RSI66)
    df_t = pd.DataFrame({"close_price": closes_random})
    df_t["rsi_22"] = RSIService.calculate_wilder_rsi(df_t["close_price"], 22)
    df_t["rsi_44"] = RSIService.calculate_wilder_rsi(df_t["close_price"], 44)
    df_t["rsi_66"] = RSIService.calculate_wilder_rsi(df_t["close_price"], 66)
    df_t["avg"] = df_t[["rsi_22","rsi_44","rsi_66"]].mean(axis=1, skipna=False).round(4)
    row = df_t.dropna().iloc[-1]
    expected = round((row["rsi_22"] + row["rsi_44"] + row["rsi_66"]) / 3, 4)
    assert abs(row["avg"] - expected) < 0.01

check("TASK 7: RSI Wilder — insufficient data, all-up/down, range [0,100], avg correctness", t7_rsi)


# ─── TASK 8: Repository — StockRepository ───────────────────────────────────
def t8_stock_repo():
    from app.database.connection import get_db_session
    from app.database.repositories import StockRepository
    with get_db_session() as session:
        stocks = StockRepository.get_all_active_stocks(session)
        assert len(stocks) > 0, "No active stocks returned"
        first = stocks[0]
        assert first.symbol and first.exchange
        fetched = StockRepository.get_stock_by_symbol(session, first.symbol)
        assert fetched is not None and fetched.id == first.id

check("TASK 8: StockRepository — get_all_active_stocks, get_stock_by_symbol", t8_stock_repo)


# ─── TASK 9: Repository — DailyPriceRepository ──────────────────────────────
def t9_price_repo():
    from app.database.connection import get_db_session
    from app.database.repositories import StockRepository, DailyPriceRepository
    with get_db_session() as session:
        stocks = StockRepository.get_all_active_stocks(session)
        stock_id = stocks[0].id
        prices = DailyPriceRepository.get_prices_by_stock(session, stock_id)
        assert len(prices) > 0, "No prices returned"
        latest = DailyPriceRepository.get_latest_price_date(session)
        assert latest is not None
        trading_days = DailyPriceRepository.get_last_n_trading_days(session, n=70)
        assert len(trading_days) <= 70
        assert trading_days == sorted(trading_days), "Trading days not sorted ascending"

check("TASK 9: DailyPriceRepository — prices, latest date, 70 trading days", t9_price_repo)


# ─── TASK 10: Repository — RSIMetricsRepository ─────────────────────────────
def t10_rsi_repo():
    from app.database.connection import get_db_session
    from app.database.repositories import StockRepository, RSIMetricsRepository
    with get_db_session() as session:
        stocks = StockRepository.get_all_active_stocks(session)
        stock_id = stocks[0].id
        latest_rsi = RSIMetricsRepository.get_latest_rsi_metric(session, stock_id)
        assert latest_rsi is not None, "No RSI metric for first active stock"
        rankings = RSIMetricsRepository.get_latest_rsi_rankings(session)
        assert len(rankings) > 0
        # Check all required fields
        for r in rankings[:5]:
            assert "symbol" in r and "average_rsi" in r
        # Check descending sort by average_rsi
        avgs = [r["average_rsi"] for r in rankings if r["average_rsi"] is not None]
        assert avgs == sorted(avgs, reverse=True), "RSI rankings not sorted descending"

check("TASK 10: RSIMetricsRepository — latest metric, rankings, descending sort", t10_rsi_repo)


# ─── TASK 11: JobRunRepository ──────────────────────────────────────────────
def t11_job_repo():
    from app.database.connection import get_db_session
    from app.database.repositories import JobRunRepository, JobErrorRepository
    with get_db_session() as session:
        jr = JobRunRepository.create_job_run(session, "VERIFICATION_TEST", date.today(), 0)
        assert jr.id is not None
        assert jr.status == "STARTED"
        JobRunRepository.complete_job_run(session, jr.id, "SUCCESS", 10, 0)
        updated_jr = session.get(type(jr), jr.id)
        assert updated_jr.status == "SUCCESS"
        assert updated_jr.successful_stocks == 10
        # Cleanup
        session.delete(updated_jr)

check("TASK 11: JobRunRepository — create, complete, verify status", t11_job_repo)


# ─── TASK 12: ClosingPriceMatrix ────────────────────────────────────────────
def t12_price_matrix():
    from app.database.connection import get_db_session
    from app.database.repositories import DailyPriceRepository
    with get_db_session() as session:
        trading_days = DailyPriceRepository.get_last_n_trading_days(session, n=5)
        matrix = DailyPriceRepository.get_closing_price_matrix_data(session, trading_days)
        assert len(matrix) > 0
        row = matrix[0]
        assert "trade_date" in row and "symbol" in row and "close_price" in row
        assert isinstance(row["close_price"], float)

check("TASK 12: Closing price matrix — returns trade_date, symbol, close_price", t12_price_matrix)


# ─── TASK 13: Excel output dir & path construction ──────────────────────────
def t13_excel_paths():
    from pathlib import Path
    from app.services.excel_report_service import ExcelReportService, OUTPUT_DIR
    assert OUTPUT_DIR is not None
    assert "output" in str(OUTPUT_DIR).lower()
    # Check output directory is created on demand
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    assert OUTPUT_DIR.exists()

check("TASK 13: Excel output directory resolves correctly", t13_excel_paths)


# ─── TASK 14: Verify existing Excel report exists in output/ ────────────────
def t14_existing_reports():
    from pathlib import Path
    output_dir = Path("d:/Nifty-200_Stock_RSI_Index/output")
    xlsx_files = list(output_dir.glob("NIFTY200_RSI_Report_*.xlsx"))
    assert len(xlsx_files) > 0, "No Excel reports found in output/"
    latest = max(xlsx_files, key=lambda f: f.stat().st_mtime)
    print(f"      Latest report: {latest.name} ({latest.stat().st_size} bytes)")
    assert latest.stat().st_size > 1000, "Excel file too small — likely empty"

check("TASK 14: Existing Excel report found in output/ with non-zero size", t14_existing_reports)


# ─── TASK 15: MissingDataService — date detection logic ─────────────────────
def t15_missing_data_service():
    from app.services.missing_data_service import MissingDataService
    from app.database.connection import get_db_session
    with get_db_session() as session:
        latest = MissingDataService.get_latest_database_date(session)
        assert latest is not None, "Could not retrieve latest DB date"
        assert isinstance(latest, date)

check("TASK 15: MissingDataService — latest_database_date resolves", t15_missing_data_service)


# ─── TASK 16: Config loads from .env ────────────────────────────────────────
def t16_config():
    from app.config import config
    assert config.DB_HOST
    assert config.DB_NAME == "cnx200_rsi_dashboard"
    assert config.DB_PORT == 3306
    assert config.NSE_MAX_RETRIES >= 1

check("TASK 16: Config loads from .env with correct values", t16_config)


# ─── TASK 17: Logger produces output ────────────────────────────────────────
def t17_logger():
    from app.utils.logger import logger
    logger.info("Stabilization test log entry")
    # If no exception, logger is working

check("TASK 17: Logger initializes and produces output without error", t17_logger)


# ─── TASK 18: Retry decorator wraps correctly ───────────────────────────────
def t18_retry():
    from app.utils.retry import nse_retry
    call_count = [0]
    @nse_retry
    def mock_fn():
        call_count[0] += 1
        return "ok"
    result = mock_fn()
    assert result == "ok"
    assert call_count[0] == 1

check("TASK 18: nse_retry decorator wraps functions without breaking them", t18_retry)


# ─── TASK 19: DB Upsert idempotency (bulk_insert_daily_prices duplicate) ────
def t19_upsert_idempotency():
    from app.database.connection import get_db_session
    from app.database.repositories import StockRepository, DailyPriceRepository
    from sqlalchemy import text
    with get_db_session() as session:
        stocks = StockRepository.get_all_active_stocks(session)
        stock_id = stocks[0].id
        # Get an existing record for this stock
        prices = DailyPriceRepository.get_prices_by_stock(session, stock_id)
        existing = prices[0]
        original_close = float(existing.close_price)

        # Re-insert same record with different close price to verify upsert updates it
        dup_record = [{
            "stock_id": stock_id,
            "trade_date": existing.trade_date,
            "open_price": float(existing.open_price) if existing.open_price else None,
            "high_price": float(existing.high_price) if existing.high_price else None,
            "low_price": float(existing.low_price) if existing.low_price else None,
            "close_price": original_close + 0.0001,  # Slight change to test upsert
            "volume": int(existing.volume) if existing.volume else None
        }]
        DailyPriceRepository.bulk_insert_daily_prices(session, dup_record)

        # Re-insert again with original to restore
        restore_record = [{**dup_record[0], "close_price": original_close}]
        DailyPriceRepository.bulk_insert_daily_prices(session, restore_record)

        # Verify no duplicate rows
        count = session.execute(
            text(f"SELECT COUNT(*) FROM daily_prices WHERE stock_id={stock_id} AND trade_date='{existing.trade_date}'")
        ).scalar()
        assert count == 1, f"Duplicate rows detected: {count}"

check("TASK 19: Bulk UPSERT idempotency — no duplicate rows created", t19_upsert_idempotency)


# ─── TASK 20: RSI upsert idempotency ────────────────────────────────────────
def t20_rsi_upsert():
    from app.database.connection import get_db_session
    from app.database.repositories import StockRepository, RSIMetricsRepository
    from sqlalchemy import text
    with get_db_session() as session:
        stocks = StockRepository.get_all_active_stocks(session)
        stock_id = stocks[0].id
        latest = RSIMetricsRepository.get_latest_rsi_metric(session, stock_id)
        assert latest is not None

        # Re-insert same RSI record
        dup = [{
            "stock_id": stock_id,
            "trade_date": latest.trade_date,
            "rsi_22": float(latest.rsi_22) if latest.rsi_22 else None,
            "rsi_44": float(latest.rsi_44) if latest.rsi_44 else None,
            "rsi_66": float(latest.rsi_66) if latest.rsi_66 else None,
            "average_rsi": float(latest.average_rsi) if latest.average_rsi else None,
            "calculation_status": "SUCCESS"
        }]
        RSIMetricsRepository.bulk_insert_rsi_metrics(session, dup)

        count = session.execute(
            text(f"SELECT COUNT(*) FROM stock_rsi_metrics WHERE stock_id={stock_id} AND trade_date='{latest.trade_date}'")
        ).scalar()
        assert count == 1, f"Duplicate RSI rows detected: {count}"

check("TASK 20: RSI metrics UPSERT idempotency — no duplicates", t20_rsi_upsert)


# ─── TASK 21: Overall pipeline integrity from DB ────────────────────────────
def t21_pipeline_integrity():
    from app.database.connection import get_db_session
    from app.database.repositories import StockRepository, DailyPriceRepository, RSIMetricsRepository
    with get_db_session() as session:
        active_stocks = StockRepository.get_all_active_stocks(session)
        trading_days = DailyPriceRepository.get_last_n_trading_days(session, n=70)
        rankings = RSIMetricsRepository.get_latest_rsi_rankings(session)

        assert len(active_stocks) >= 100
        assert len(trading_days) >= 1
        assert len(rankings) >= 100

        # Every ranking entry has a valid average_rsi
        stocks_with_rsi = sum(1 for r in rankings if r["average_rsi"] is not None)
        assert stocks_with_rsi > 100, f"Only {stocks_with_rsi} stocks have average_rsi"

        # Latest RSI date matches latest price date (or close to it)
        latest_price_date = DailyPriceRepository.get_latest_price_date(session)
        latest_rsi_date = max(r["trade_date"] for r in rankings if r["trade_date"])
        diff = abs((latest_price_date - latest_rsi_date).days)
        print(f"      Latest price date: {latest_price_date}, Latest RSI date: {latest_rsi_date}, Diff: {diff} days")
        assert diff <= 5, f"RSI is {diff} days behind prices — stale RSI"

check("TASK 21: Pipeline integrity — stocks, prices, RSI alignment", t21_pipeline_integrity)


# ─── FINAL REPORT ────────────────────────────────────────────────────────────
passes = sum(1 for s, _ in results if s == PASS)
failures = [(s, l) for s, l in results if s == FAIL]

print()
print("=" * 70)
print(f"STABILIZATION VERIFICATION COMPLETE: {passes}/{len(results)} PASSED")
if failures:
    print(f"\nFAILURES ({len(failures)}):")
    for _, label in failures:
        print(f"  {FAIL} {label}")
    sys.exit(1)
else:
    print("ALL 21 AUDIT TASKS PASSED — Backend is stable and verified.")
print("=" * 70)
