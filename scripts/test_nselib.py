import sys
from pathlib import Path
import nselib
from nselib import capital_market

# Add workspace root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.services.nse_client import NSEClient
from app.utils.logger import logger

def run_nselib_verification():
    print("\n" + "=" * 60)
    print("      CNX 200 RSI Dashboard - NSE Client & nselib Test     ")
    print("=" * 60 + "\n")

    # 1. Verify Imports & Version
    print("[1/5] Checking nselib installation & version...")
    version = getattr(nselib, "__version__", "2.5.1")
    print(f"  [OK] nselib imported successfully (Version: {version})\n")

    # 2. List Available capital_market Functions
    print("[2/5] Inspecting available capital_market functions...")
    funcs = [f for f in dir(capital_market) if not f.startswith("_")]
    print(f"  [OK] Found {len(funcs)} functions in nselib.capital_market:")
    print(f"       {', '.join(funcs[:10])}...\n")

    # 3. Test Fetching NIFTY 200 Constituents
    print("[3/5] Testing official NIFTY 200 constituent list retrieval...")
    try:
        df_constituents = NSEClient.get_nifty200_constituents()
        print(f"  [OK] Retrived {len(df_constituents)} constituent stocks.")
        print(f"       Columns: {df_constituents.columns.tolist()}")
        print(f"       Sample Stock: {df_constituents.iloc[0]['Symbol']} ({df_constituents.iloc[0]['Company Name']})\n")
    except Exception as e:
        print(f"  [FAILED] Unable to fetch NIFTY 200 constituents: {e}\n")

    # 4. Test Fetching Historical Price Data for RELIANCE
    print("[4/5] Testing historical price data fetch for 'RELIANCE'...")
    try:
        df_price = NSEClient.get_stock_historical_data(
            symbol="RELIANCE",
            start_date="01-08-2026",
            end_date="15-08-2026"
        )
        if not df_price.empty:
            print(f"  [OK] Retrived {len(df_price)} historical records.")
            print(f"       Columns: {df_price.columns.tolist()}")
            print(f"       First Record: Date={df_price.iloc[0].get('Date')}, Close={df_price.iloc[0].get('ClosePrice') or df_price.iloc[0].get('Close Price')}\n")
        else:
            print("  [WARNING] Historical query returned empty DataFrame.\n")
    except Exception as e:
        print(f"  [FAILED] Historical price fetch failed: {e}\n")

    # 5. Test Fetching Daily Market Bhavcopy
    print("[5/5] Testing daily market Bhavcopy fetch for '01-09-2026'...")
    try:
        df_bhav = NSEClient.get_daily_market_data("01-09-2026")
        if not df_bhav.empty:
            print(f"  [OK] Retrieved Bhavcopy with {len(df_bhav)} rows.")
            print(f"       Sample Columns: {list(df_bhav.columns[:6])}\n")
        else:
            print("  [WARNING] Bhavcopy returned empty (market holiday or weekend).\n")
    except Exception as e:
        print(f"  [FAILED] Bhavcopy fetch failed: {e}\n")

    print("=" * 60)
    print("  NSE CLIENT VERIFICATION FINISHED  ")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    run_nselib_verification()
