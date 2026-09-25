import argparse
from app.database.init_db import init_database
from app.services.ingestion_service import IngestionService
from app.services.rsi_service import RSIService
from app.services.excel_report_service import ExcelReportService


def main():
    parser = argparse.ArgumentParser(description="NIFTY 200 RSI MongoDB data pipeline")
    parser.add_argument("--init-db", action="store_true", help="Initialize MongoDB collections and indexes")
    parser.add_argument("--sync-universe", action="store_true", help="Sync NIFTY 200 universe from NSE")
    parser.add_argument("--backfill-historical", action="store_true", help="Backfill historical price data")
    parser.add_argument("--recover-missing", action="store_true", help="Update missing market data")
    parser.add_argument("--compute-rsi", action="store_true", help="Compute RSI metrics for active stocks")
    parser.add_argument("--generate-excel", action="store_true", help="Generate real-time Excel report")
    parser.add_argument("--start-date", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", help="End date (YYYY-MM-DD)")
    parser.add_argument("--symbols", nargs="+", help="Specific symbols to process")

    args = parser.parse_args()

    if args.init_db:
        success = init_database()
        print("Database initialized successfully." if success else "Database initialization failed.")
    if args.sync_universe:
        print(IngestionService.sync_stock_universe())
    if args.backfill_historical:
        print(IngestionService.backfill_historical_data(args.start_date, args.end_date, args.symbols))
    if args.recover_missing:
        print(IngestionService.update_missing_market_data(args.start_date, args.end_date))
    if args.compute_rsi:
        print(RSIService.compute_all_active_stocks_rsi())
    if args.generate_excel:
        RSIService.compute_all_active_stocks_rsi()
        print(ExcelReportService.generate_nifty200_excel_report(refresh_market_data=False, end_date=args.end_date))

    flags = ("init_db", "sync_universe", "backfill_historical", "recover_missing", "compute_rsi", "generate_excel")
    if not any(vars(args).get(flag) for flag in flags):
        parser.print_help()


if __name__ == "__main__":
    main()
