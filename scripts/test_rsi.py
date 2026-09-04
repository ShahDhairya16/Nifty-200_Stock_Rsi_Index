import sys
from pathlib import Path

# Add workspace root to python path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.database.connection import get_db_session
from app.database.init_db import init_database
from app.database.repositories import StockRepository, DailyPriceRepository, RSIMetricsRepository
from app.services.rsi_service import RSIService
from app.utils.logger import logger

def test_rsi_for_reliance():
    print("\n" + "=" * 60)
    print("           Testing RSI Calculation & Storage (RELIANCE)      ")
    print("=" * 60 + "\n")

    if not init_database():
        print("[FAILED] Database initialization failed.")
        sys.exit(1)

    print("Testing RSI Calculation\n")
    print("Stock: RELIANCE\n")

    with get_db_session() as session:
        stock = StockRepository.get_stock_by_symbol(session, "RELIANCE")
        if not stock:
            print("[FAILED] Stock RELIANCE not found in database. Run universe sync first.")
            sys.exit(1)

        prices = DailyPriceRepository.get_prices_by_stock(session, stock.id)
        records_available = len(prices)
        print(f"Records Available: {records_available}\n")

        # Compute & store RSI metrics in stock_rsi_metrics table
        res = RSIService.compute_and_store_rsi_for_stock(session, stock.id)
        if res["status"] != "SUCCESS":
            print(f"[FAILED] RSI calculation failed: {res.get('reason')}")
            sys.exit(1)

        # Retrieve latest calculated RSI metric from database
        latest_rsi = RSIMetricsRepository.get_latest_rsi_metric(session, stock.id)

        if latest_rsi:
            rsi22_str = f"{float(latest_rsi.rsi_22):.2f}" if latest_rsi.rsi_22 is not None else "N/A"
            rsi44_str = f"{float(latest_rsi.rsi_44):.2f}" if latest_rsi.rsi_44 is not None else "N/A"
            rsi66_str = f"{float(latest_rsi.rsi_66):.2f}" if latest_rsi.rsi_66 is not None else "N/A"
            avg_rsi_str = f"{float(latest_rsi.average_rsi):.2f}" if latest_rsi.average_rsi is not None else "N/A"

            print(f"RSI 22: {rsi22_str}")
            print(f"RSI 44: {rsi44_str}")
            print(f"RSI 66: {rsi66_str}\n")
            print(f"Average RSI: {avg_rsi_str}\n")
            print("Database Storage: SUCCESS\n")
        else:
            print("[FAILED] Could not retrieve calculated RSI metric from database.")
            sys.exit(1)

    print("=" * 60)
    print("  RELIANCE RSI TEST PASSED SUCCESSFULLY!  ")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    test_rsi_for_reliance()
