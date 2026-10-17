import sys
from pathlib import Path
import json
import time
import pandas as pd

# Add workspace root to python path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.database.connection import check_db_connection
from app.database.init_db import init_database
from app.database.repositories import StockRepository, PriceRepository, RSIRepository
from app.utils.logger import logger


def migrate():
    print("\n" + "=" * 65)
    print("      NIFTY 200 RSI Dashboard - Migration to MongoDB      ")
    print("=" * 65 + "\n")

    if not check_db_connection():
        print("[ERROR] Cannot connect to MongoDB. Ensure MongoDB service is running.")
        sys.exit(1)

    print("[1/4] Initializing MongoDB collections and indexes...")
    if not init_database():
        print("[ERROR] Database initialization failed.")
        sys.exit(1)
    print("      MongoDB collections and indexes ensured.\n")

    data_dir = BASE_DIR / "data"
    stocks_file = data_dir / "stocks.json"
    prices_file = data_dir / "prices.csv"
    rsi_file = data_dir / "rsi.csv"

    # 1. Stocks migration
    start_time = time.time()
    if stocks_file.exists():
        print(f"[2/4] Migrating stocks from {stocks_file.name}...")
        stocks = json.loads(stocks_file.read_text(encoding="utf-8"))
        count = StockRepository.bulk_upsert_stocks(stocks)
        print(f"      Successfully upserted {count} stocks (Total in DB: {StockRepository.count_stocks()}).\n")
    else:
        print(f"[2/4] No {stocks_file.name} found. Skipping stocks file migration.\n")

    # 2. Prices migration
    if prices_file.exists():
        print(f"[3/4] Migrating price records from {prices_file.name}...")
        df_prices = pd.read_csv(prices_file)
        print(f"      Read {len(df_prices)} price records from CSV. Bulk writing to MongoDB...")
        count = PriceRepository.bulk_upsert_prices(df_prices, batch_size=5000)
        print(f"      Successfully upserted {count} price records (Total in DB: {PriceRepository.count_prices()}).\n")
    else:
        print(f"[3/4] No {prices_file.name} found. Skipping price records migration.\n")

    # 3. RSI migration
    if rsi_file.exists():
        print(f"[4/4] Migrating RSI records from {rsi_file.name}...")
        df_rsi = pd.read_csv(rsi_file)
        print(f"      Read {len(df_rsi)} RSI records from CSV. Bulk writing to MongoDB...")
        count = RSIRepository.bulk_upsert_rsi(df_rsi, batch_size=5000)
        print(f"      Successfully upserted {count} RSI records (Total in DB: {RSIRepository.count_rsi()}).\n")
    else:
        print(f"[4/4] No {rsi_file.name} found. Skipping RSI records migration.\n")

    total_time = time.time() - start_time
    print("=" * 65)
    print(f"Migration completed in {total_time:.2f} seconds!")
    print(f"Summary:")
    print(f"  - Stocks count: {StockRepository.count_stocks()} ({StockRepository.count_stocks(active_only=True)} active)")
    print(f"  - Prices count: {PriceRepository.count_prices():,}")
    print(f"  - RSI count:    {RSIRepository.count_rsi():,}")
    print(f"  - Latest date:  {PriceRepository.latest_price_date()}")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    migrate()
