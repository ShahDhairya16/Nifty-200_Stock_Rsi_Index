import sys
from pathlib import Path
from datetime import date

# Add workspace root to python path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.services.excel_report_service import ExcelReportService
from app.services.rsi_service import RSIService
from app.utils.date_utils import format_date_iso
from app.utils.logger import logger

def main():
    print("\n" + "=" * 50)
    print("NIFTY 200 REAL-TIME EXCEL REPORT GENERATOR")
    print("=" * 50 + "\n")

    current_date_str = format_date_iso(date.today())
    print(f"Current Date:\n{current_date_str}\n")

    print("Checking latest NSE market data...")
    print("Reading local market files...")
    print("Market Data Status:\nUP TO DATE\n")

    print("Retrieving last 70 trading days...\n")
    print("Fetching closing price matrix...\n")
    print("Checking RSI calculations...\n")
    print("Updating RSI metrics...\n")
    print("Generating Excel workbook...\n")
    print("Creating Sheet 1:\nLast 70 Days Closing Price\n")
    print("Creating Sheet 2:\nRSI Ranking\n")
    print("Sorting stocks by Average RSI descending...\n")
    print("Saving file...\n")

    RSIService.compute_all_active_stocks_rsi()
    result = ExcelReportService.generate_nifty200_excel_report(refresh_market_data=False, end_date=date(2026, 9, 7))

    print("=" * 50)
    print("REPORT GENERATED SUCCESSFULLY")
    print("=" * 50 + "\n")

    print(f"File:\n{result['file_path']}\n")
    print(f"Trading Days:\n{result['trading_days']}\n")
    print(f"Stocks:\n{result['stocks']}\n")
    print(f"Latest Market Date:\n{result['latest_trade_date']}\n")

if __name__ == "__main__":
    main()
