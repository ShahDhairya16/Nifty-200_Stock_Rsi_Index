import sys
from datetime import date
from pathlib import Path
from sqlalchemy import inspect, text

# Add workspace root to python path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.config import config
from app.database.connection import get_db_session, get_engine, check_db_connection
from app.database.init_db import init_database
from app.database.repositories import (
    StockRepository,
    DailyPriceRepository,
    JobRunRepository,
    JobErrorRepository,
    DataFetchLogRepository,
)
from app.utils.logger import logger

def run_database_tests():
    print("\n" + "=" * 60)
    print("      CNX 200 RSI Dashboard - Database Verification Test     ")
    print("=" * 60 + "\n")

    # Step 1: Initialize Database & Ensure Connection
    print("[1/11] Initializing database schema and checking connection...")
    if not init_database():
        print("[FAILED] Database initialization failed.")
        sys.exit(1)
    
    if not check_db_connection():
        print("[FAILED] Unable to establish database connection.")
        sys.exit(1)
    print("  [OK] Connected to MySQL successfully.\n")

    # Step 2 & 3: Verify Tables Exist
    print("[2/11 & 3/11] Verifying database existence and table structure...")
    engine = get_engine(with_db=True)
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    
    required_tables = {"stock_master", "daily_prices", "job_runs", "job_errors", "data_fetch_log"}
    missing_tables = required_tables - existing_tables
    
    if missing_tables:
        print(f"[FAILED] Missing required tables: {missing_tables}")
        sys.exit(1)
    print(f"  [OK] Verified database '{config.DB_NAME}' contains all required tables: {sorted(list(required_tables))}\n")

    with get_db_session() as session:
        # Step 4: Insert sample stocks
        print("[4/11] Inserting sample stocks (RELIANCE, TCS)...")
        stock_reliance = StockRepository.add_stock(
            session, symbol="RELIANCE", company_name="Reliance Industries Ltd.", exchange="NSE"
        )
        stock_tcs = StockRepository.add_stock(
            session, symbol="TCS", company_name="Tata Consultancy Services Ltd.", exchange="NSE"
        )
        print(f"  [OK] Inserted/Retrieved stock RELIANCE (ID: {stock_reliance.id})")
        print(f"  [OK] Inserted/Retrieved stock TCS (ID: {stock_tcs.id})\n")

        # Step 5: Insert sample daily price
        print("[5/11] Inserting sample daily price record for RELIANCE (2026-09-01)...")
        trade_date_1 = date(2026, 9, 1)
        price_1 = DailyPriceRepository.insert_daily_price(
            session=session,
            stock_id=stock_reliance.id,
            trade_date=trade_date_1,
            open_price=1400.00,
            high_price=1420.00,
            low_price=1395.00,
            close_price=1412.50,
            volume=1500000
        )
        print(f"  [OK] Inserted DailyPrice record: {price_1}\n")

        # Step 6 & 7: Test duplicate prevention / UPSERT behavior
        print("[6/11 & 7/11] Testing UPSERT & duplicate prevention for RELIANCE on 2026-09-01...")
        # Re-insert same stock_id and trade_date with updated close price 1425.00
        updated_price = DailyPriceRepository.insert_daily_price(
            session=session,
            stock_id=stock_reliance.id,
            trade_date=trade_date_1,
            open_price=1400.00,
            high_price=1430.00,  # Updated high
            low_price=1395.00,
            close_price=1425.00, # Updated close
            volume=1600000
        )
        
        # Verify row count for (stock_id, trade_date)
        all_prices = DailyPriceRepository.get_prices_by_stock(session, stock_reliance.id)
        matching_rows = [p for p in all_prices if p.trade_date == trade_date_1]
        
        if len(matching_rows) == 1 and float(matching_rows[0].close_price) == 1425.00:
            print(f"  [OK] Duplicate prevention / UPSERT verified: Row count = {len(matching_rows)}, Updated Close = {matching_rows[0].close_price}\n")
        else:
            print(f"[FAILED] Duplicate prevention test failed! Rows found: {len(matching_rows)}")
            sys.exit(1)

        # Step 8: Retrieve latest trade date
        print("[8/11] Retrieving latest trade date...")
        latest_date = DailyPriceRepository.get_latest_price_date(session)
        print(f"  [OK] Latest trade date in database: {latest_date}\n")

        # Step 9: Create sample job run
        print("[9/11] Creating a sample job run...")
        job_run = JobRunRepository.create_job_run(
            session=session,
            job_name="Daily Market Update",
            run_date=date.today(),
            expected_stocks=200
        )
        print(f"  [OK] Created JobRun (ID: {job_run.id}, Status: {job_run.status})\n")

        # Step 10: Insert sample job error & complete job run
        print("[10/11] Logging sample job error and completing job run...")
        job_error = JobErrorRepository.log_job_error(
            session=session,
            job_run_id=job_run.id,
            stock_id=stock_tcs.id,
            error_type="API_TIMEOUT",
            error_message="Connection timed out while fetching NSE price data.",
            retry_attempt=1
        )
        print(f"  [OK] Logged JobError (ID: {job_error.id}, Error: {job_error.error_type})")

        completed_job = JobRunRepository.complete_job_run(
            session=session,
            job_run_id=job_run.id,
            status="PARTIAL_SUCCESS",
            successful_stocks=199,
            failed_stocks=1,
            error_message="1 stock failed due to API timeout."
        )
        print(f"  [OK] Completed JobRun (ID: {completed_job.id}, Status: {completed_job.status})\n")

        # Step 11: Final Summary Output
        print("[11/11] Summary Verification:")
        active_stocks = StockRepository.get_all_active_stocks(session)
        errors = JobErrorRepository.get_errors_by_job_run(session, job_run.id)
        
        print(f"  - Total Active Stocks in StockMaster: {len(active_stocks)}")
        print(f"  - Total Job Errors logged for Job {job_run.id}: {len(errors)}")
        print("\n" + "=" * 60)
        print("  ALL DATABASE LAYER TESTS PASSED SUCCESSFULLY!  ")
        print("=" * 60 + "\n")

if __name__ == "__main__":
    run_database_tests()
