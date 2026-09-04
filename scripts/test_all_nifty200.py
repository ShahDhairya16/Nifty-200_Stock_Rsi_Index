import sys
from pathlib import Path
from datetime import date, timedelta

# Add workspace root to python path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.database.connection import get_db_session
from app.database.init_db import init_database
from app.database.repositories import StockRepository, DailyPriceRepository, RSIMetricsRepository
from app.services.stock_universe_service import StockUniverseService
from app.services.historical_data_service import HistoricalDataService
from app.services.rsi_service import RSIService
from app.utils.logger import logger

def run_test_all_nifty200():
    print("\n" + "=" * 60)
    print("       NIFTY 200 TEST INGESTION & RSI METRICS PIPELINE      ")
    print("=" * 60 + "\n")

    if not init_database():
        print("[FAILED] Database initialization failed.")
        sys.exit(1)

    print("NIFTY 200 TEST INGESTION\n")

    # Step 1: Universe Sync
    summary_sync = StockUniverseService.sync_nifty200_universe()
    total_stocks = summary_sync["total_fetched"] or 200
    print(f"Total Stocks: ~{total_stocks}\n")

    with get_db_session() as session:
        active_stocks = StockRepository.get_all_active_stocks(session)
        print(f"Fetching recent market data (~90-100 trading days) and calculating RSI...\n")

        successful_count = 0
        failed_count = 0
        total_price_records = 0
        total_rsi_records = 0

        end_date = date.today()
        start_date = end_date - timedelta(days=130)  # Buffer to ensure RSI 66 computation

        for idx, stock in enumerate(active_stocks, 1):
            sym = stock.symbol
            try:
                # 1. Fetch recent prices
                res_price = HistoricalDataService.backfill_historical_data(
                    start_date=start_date,
                    end_date=end_date,
                    symbols=[sym],
                    session=session
                )
                
                prices = DailyPriceRepository.get_prices_by_stock(session, stock.id)
                price_cnt = len(prices)
                total_price_records += price_cnt

                # 2. Calculate & store RSI
                res_rsi = RSIService.compute_and_store_rsi_for_stock(session, stock.id)
                rsi_cnt = res_rsi.get("upserted", 0)
                total_rsi_records += rsi_cnt

                if res_rsi["status"] == "SUCCESS":
                    print(f"[{idx}/{len(active_stocks)}] {sym:<12} | Prices: {price_cnt:<4} | RSI: SUCCESS ({rsi_cnt} records)")
                    successful_count += 1
                else:
                    print(f"[{idx}/{len(active_stocks)}] {sym:<12} | Prices: {price_cnt:<4} | RSI: {res_rsi.get('status')} ({res_rsi.get('reason')})")
                    failed_count += 1

            except Exception as e:
                print(f"[{idx}/{len(active_stocks)}] {sym:<12} | Prices: FAILED | RSI: FAILED ({e})")
                failed_count += 1

        print("\n" + "=" * 60)
        print("                        FINAL SUMMARY                       ")
        print("=" * 60)
        print(f"Stocks Processed: {len(active_stocks)}")
        print(f"Successful: {successful_count}")
        print(f"Failed: {failed_count}\n")
        print(f"Price Records Stored: {total_price_records}")
        print(f"RSI Records Stored: {total_rsi_records}")
        print("=" * 60 + "\n")

        print("Verification SQL Queries:\n")
        print("1. Check total active stocks:")
        print("   SELECT COUNT(*) FROM stock_master WHERE active = TRUE;\n")
        print("2. Check price records count per stock:")
        print("   SELECT sm.symbol, COUNT(dp.id) AS price_records FROM stock_master sm LEFT JOIN daily_prices dp ON dp.stock_id = sm.id GROUP BY sm.symbol ORDER BY price_records DESC;\n")
        print("3. Check latest price records:")
        print("   SELECT sm.symbol, dp.trade_date, dp.close_price FROM daily_prices dp JOIN stock_master sm ON sm.id = dp.stock_id ORDER BY dp.trade_date DESC LIMIT 10;\n")
        print("4. Check calculated RSI metrics:")
        print("   SELECT sm.symbol, r.trade_date, r.rsi_22, r.rsi_44, r.rsi_66, r.average_rsi FROM stock_rsi_metrics r JOIN stock_master sm ON sm.id = r.stock_id ORDER BY r.trade_date DESC, r.average_rsi DESC LIMIT 10;\n")

if __name__ == "__main__":
    run_test_all_nifty200()
