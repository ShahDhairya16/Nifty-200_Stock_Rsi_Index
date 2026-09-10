import sys
from pathlib import Path

# Add workspace root to python path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.services.stock_universe_service import StockUniverseService
from app.utils.logger import logger

def main():
    print("\n" + "=" * 60)
    print("      CNX 200 RSI Dashboard - Stock Universe Synchronization     ")
    print("=" * 60 + "\n")

    print("Starting NIFTY 200 Universe Sync...\n")
    print("Fetching latest NIFTY 200 constituents...\n")

    summary = StockUniverseService.sync_nifty200_universe()

    if summary["errors"]:
        print(f"[FAILED] Universe sync encountered errors: {summary['errors']}")
        sys.exit(1)

    print(f"Fetched: {summary['total_fetched']} stocks\n")
    print(f"New Stocks: {summary['new_stocks']}")
    print(f"Updated Stocks: {summary['updated_stocks']}")
    print(f"Deactivated Stocks: {summary['deactivated_stocks']}\n")

    print("Sync completed successfully.\n")

if __name__ == "__main__":
    main()
