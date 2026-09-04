import sys
from pathlib import Path
from datetime import date, timedelta

# Add workspace root to python path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.database.connection import get_db_session
from app.database.init_db import init_database
from app.database.repositories import StockRepository, DailyPriceRepository
from app.services.historical_data_service import HistoricalDataService
from app.services.stock_universe_service import StockUniverseService
from app.utils.date_utils import format_date_iso
from app.utils.logger import logger

def test_recent_data_for_reliance():
    print("\n" + "=" * 60)
    print("         Testing NSE Historical Data (Recent 90 Days)        ")
    print("=" * 60 + "\n")

    if not init_database():
        print("[FAILED] Database initialization failed.")
        sys.exit(1)

    with get_db_session() as session:
        # Ensure RELIANCE stock exists in stock_master
        stock = StockRepository.get_stock_by_symbol(session, "RELIANCE")
        if not stock:
            print("Stock RELIANCE not found in DB. Synchronizing universe...")
            StockUniverseService.sync_nifty200_universe(session)
            stock = StockRepository.get_stock_by_symbol(session, "RELIANCE")

        print("Testing NSE Historical Data\n")
        print(f"Stock: {stock.symbol}\n")

        end_date = date.today()
        start_date = end_date - timedelta(days=120)  # ~90-100 trading days buffer

        res = HistoricalDataService.backfill_historical_data(
            start_date=start_date,
            end_date=end_date,
            symbols=["RELIANCE"],
            session=session
        )

        prices = DailyPriceRepository.get_prices_by_stock(session, stock.id)

        if prices:
            first_date = prices[0].trade_date
            last_date = prices[-1].trade_date
            print(f"Records fetched: {len(prices)}\n")
            print(f"First Date: {format_date_iso(first_date)}")
            print(f"Last Date: {format_date_iso(last_date)}\n")

            print("Sample:\n")
            print(f"{'Date':<15} {'Close':<10}")
            print("-" * 25)
            for p in prices[-10:]:
                print(f"{format_date_iso(p.trade_date):<15} {float(p.close_price):<10.2f}")
            print("-" * 25 + "\n")
        else:
            print("[FAILED] No price records retrieved for RELIANCE.\n")

if __name__ == "__main__":
    test_recent_data_for_reliance()
