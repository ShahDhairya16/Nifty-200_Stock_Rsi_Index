import argparse
from app.services.ingestion_service import IngestionService
from app.services.rsi_service import RSIService
from app.services.excel_report_service import ExcelReportService


def main():
    parser = argparse.ArgumentParser(description="NIFTY 200 RSI file-based data pipeline")
    parser.add_argument("--sync-universe", action="store_true")
    parser.add_argument("--backfill-historical", action="store_true")
    parser.add_argument("--recover-missing", action="store_true")
    parser.add_argument("--generate-excel", action="store_true")
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--symbols", nargs="+")
    args = parser.parse_args()
    if args.sync_universe:
        print(IngestionService.sync_stock_universe())
    if args.backfill_historical:
        print(IngestionService.backfill_historical_data(args.start_date, args.end_date, args.symbols))
    if args.recover_missing:
        print(IngestionService.update_missing_market_data(args.start_date, args.end_date))
    if args.generate_excel:
        RSIService.compute_all_active_stocks_rsi()
        print(ExcelReportService.generate_nifty200_excel_report(refresh_market_data=False, end_date=args.end_date))
    if not any(vars(args).get(flag) for flag in ("sync_universe", "backfill_historical", "recover_missing", "generate_excel")):
        parser.print_help()


if __name__ == "__main__":
    main()
