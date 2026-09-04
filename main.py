import argparse
import sys
from app.database.init_db import init_database
from app.services.ingestion_service import IngestionService
from app.utils.logger import logger
from scripts.test_database import run_database_tests
from scripts.test_nselib import run_nselib_verification

def main():
    parser = argparse.ArgumentParser(
        description="CNX 200 Stock RSI Dashboard - Backend Data Ingestion & Management CLI"
    )
    parser.add_argument(
        "--init-db", action="store_true", help="Initialize database and create schema tables if missing."
    )
    parser.add_argument(
        "--test-db", action="store_true", help="Run database layer verification tests."
    )
    parser.add_argument(
        "--test-nselib", action="store_true", help="Test nselib connectivity and NSE data fetching."
    )
    parser.add_argument(
        "--sync-universe", action="store_true", help="Synchronize NIFTY 200 stock universe into stock_master."
    )
    parser.add_argument(
        "--backfill-historical", action="store_true", help="Backfill historical daily market data for active stocks."
    )
    parser.add_argument(
        "--recover-missing", action="store_true", help="Detect missing trading dates and backfill missing data."
    )
    parser.add_argument(
        "--generate-excel", action="store_true", help="Generate Excel report with 70 days closing prices and RSI rankings."
    )
    parser.add_argument(
        "--start-date", type=str, default=None, help="Start date for backfill (YYYY-MM-DD)."
    )
    parser.add_argument(
        "--end-date", type=str, default=None, help="End date for backfill (YYYY-MM-DD)."
    )
    parser.add_argument(
        "--symbols", type=str, nargs="+", default=None, help="Optional specific stock symbols for backfill."
    )

    args = parser.parse_args()

    # If no flags passed, display help and execute DB test by default
    if not any([args.init_db, args.test_db, args.test_nselib, args.sync_universe, args.backfill_historical, args.recover_missing, args.generate_excel]):
        logger.info("No specific flags provided. Initializing database and running connectivity tests...")
        if init_database():
            run_database_tests()
        else:
            sys.exit(1)
        return

    if args.init_db:
        if not init_database():
            sys.exit(1)

    if args.test_db:
        run_database_tests()

    if args.test_nselib:
        run_nselib_verification()

    if args.sync_universe:
        if not init_database():
            sys.exit(1)
        logger.info("Starting NIFTY 200 Universe Synchronization...")
        IngestionService.sync_stock_universe()

    if args.backfill_historical:
        if not init_database():
            sys.exit(1)
        logger.info("Starting Historical Market Data Backfill...")
        IngestionService.backfill_historical_data(
            start_date=args.start_date,
            end_date=args.end_date,
            symbols=args.symbols
        )

    if args.recover_missing:
        if not init_database():
            sys.exit(1)
        logger.info("Starting Missing Market Data Recovery...")
        IngestionService.update_missing_market_data(
            start_date=args.start_date,
            end_date=args.end_date
        )

    if args.generate_excel:
        from app.services.excel_report_service import ExcelReportService
        if not init_database():
            sys.exit(1)
        logger.info("Starting Excel Report Generation...")
        ExcelReportService.generate_nifty200_excel_report(refresh_market_data=True)

if __name__ == "__main__":
    main()
