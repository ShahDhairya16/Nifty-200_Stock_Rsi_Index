import sys
from pathlib import Path

# Add workspace root to python path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.database.connection import check_db_connection, get_database
from app.database.repositories import StockRepository, PriceRepository, RSIRepository


def test_mongo():
    print("\n" + "=" * 60)
    print("      Testing MongoDB Connection and Repositories      ")
    print("=" * 60 + "\n")

    print("[1] Pinging MongoDB server...")
    if not check_db_connection():
        print("[FAIL] Could not connect to MongoDB!")
        sys.exit(1)
    print("[OK] MongoDB server responded to ping.\n")

    db = get_database()
    print(f"[2] Active Database: '{db.name}'")
    collections = db.list_collection_names()
    print(f"    Existing collections: {collections}\n")

    print("[3] Testing StockRepository...")
    stocks = StockRepository.get_all_stocks()
    active_stocks = StockRepository.get_active_stocks()
    print(f"[OK] Total stocks: {len(stocks)}, Active stocks: {len(active_stocks)}")
    if active_stocks:
        print(f"     Sample stock: {active_stocks[0]['symbol']} - {active_stocks[0].get('company_name')}\n")

    print("[4] Testing PriceRepository...")
    latest_date = PriceRepository.latest_price_date()
    total_prices = PriceRepository.count_prices()
    print(f"[OK] Total prices: {total_prices:,}")
    print(f"     Latest price date: {latest_date}")
    if active_stocks:
        sym = active_stocks[0]["symbol"]
        sym_prices = PriceRepository.get_prices_for_symbol(sym)
        print(f"     Sample prices for '{sym}': {len(sym_prices)} records\n")

    print("[5] Testing RSIRepository...")
    total_rsi = RSIRepository.count_rsi()
    print(f"[OK] Total RSI records: {total_rsi:,}")
    rankings = RSIRepository.get_latest_rsi_rankings()
    print(f"     RSI Rankings loaded: {len(rankings)} active stocks ranked")
    if not rankings.empty:
        top_stock = rankings.iloc[0]
        print(f"     #1 Ranked: {top_stock['symbol']} ({top_stock.get('company_name', '')}) - Average RSI: {top_stock['average_rsi']}")

    print("\n" + "=" * 60)
    print("      All MongoDB Tests Passed Successfully!      ")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    test_mongo()
