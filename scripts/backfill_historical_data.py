import sys
import argparse
from pathlib import Path

# Add workspace root to python path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.services.ingestion_service import IngestionService
from app.utils.date_utils import parse_date, get_default_start_date, format_date_iso
from app.utils.logger import logger

def main():
    parser = argparse.ArgumentParser(
        description="CNX 200 RSI Dashboard - Historical Market Data Backfill"
    )
    parser.add_argument(
        "--start-date", type=str, default=None,
        help="Start date for backfill (YYYY-MM-DD or DD-MM-YYYY). Default: 1 year prior."
    )
    parser.add_argument(
        "--end-date", type=str, default=None,
        help="End date for backfill (YYYY-MM-DD or DD-MM-YYYY). Default: Today."
    )
    parser.add_argument(
        "--symbols", type=str, nargs="+", default=None,
        help="Optional list of specific stock symbols to backfill (e.g. --symbols RELIANCE TCS INFY)."
    )

    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("      CNX 200 RSI Dashboard - Historical Data Backfill     ")
    print("=" * 60 + "\n")

    start = parse_date(args.start_date) if args.start_date else get_default_start_date(years_back=1)
    end = parse_date(args.end_date) if args.end_date else parse_date("today") or get_default_start_date(0)

    print(f"Starting Historical Backfill...\n")
    print(f"Date Range: {format_date_iso(start)} -> {format_date_iso(end)}")
    if args.symbols:
        print(f"Target Symbols: {', '.join(args.symbols)}")
    print("\nProcessing...\n")

    summary = IngestionService.backfill_historical_data(
        start_date=start,
        end_date=end,
        symbols=args.symbols
    )

    print("\n" + "=" * 60)
    print("                      Final Summary                       ")
    print("=" * 60)
    print(f"Stocks Processed: {summary['total_stocks']}")
    print(f"Successful: {summary['successful_stocks']}")
    print(f"Failed: {summary['failed_stocks']}")
    print(f"Total Price Records Upserted: {summary['total_records_processed']}")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    main()
