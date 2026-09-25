from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Optional
import openpyxl
import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill

from app.database.repositories import StockRepository, PriceRepository, RSIRepository
from app.utils.date_utils import format_date_iso, parse_date

BASE_DIR = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = BASE_DIR / "output"


class ExcelReportService:
    """Generate Excel reports from MongoDB market data."""

    @staticmethod
    def generate_nifty200_excel_report(
        output_dir: Optional[Path] = None,
        refresh_market_data: bool = True,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        report_end = parse_date(end_date) if end_date is not None else date.today()
        prices = PriceRepository.load_prices(end_date=report_end)
        if prices.empty:
            raise ValueError("No market data found in MongoDB. Run --sync-universe and --backfill-historical first.")

        dates = sorted(prices["trade_date"].unique())[-70:]
        prices = prices[prices["trade_date"].isin(dates)]
        stocks = StockRepository.get_active_stocks()
        symbols = sorted(stock["symbol"] for stock in stocks)
        matrix = prices.pivot_table(index="trade_date", columns="symbol", values="close_price").reindex(columns=symbols).reset_index()

        rsi = RSIRepository.load_rsi(end_date=report_end)
        latest = rsi.sort_values("trade_date").groupby("symbol", as_index=False).tail(1)
        names = {stock["symbol"]: stock.get("company_name") or stock["symbol"] for stock in stocks}
        ranking = latest.assign(company_name=latest["symbol"].map(names)).sort_values("average_rsi", ascending=False)
        ranking.insert(0, "Rank", range(1, len(ranking) + 1))
        ranking = ranking.rename(columns={"trade_date": "Latest Date"})[
            ["Rank", "symbol", "company_name", "Latest Date", "rsi_22", "rsi_44", "rsi_66", "average_rsi"]
        ]
        ranking.columns = ["Rank", "Symbol", "Company Name", "Latest Date", "RSI 22", "RSI 44", "RSI 66", "Average RSI"]

        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "Last 70 Days Closing Price"
        sheet.append(["Date"] + symbols)
        for row in matrix.itertuples(index=False, name=None):
            sheet.append([row[0].strftime("%d-%b-%Y")] + list(row[1:]))

        rank_sheet = workbook.create_sheet("RSI Ranking")
        rank_sheet.append(list(ranking.columns))
        for row in ranking.itertuples(index=False, name=None):
            rank_sheet.append(list(row))

        header_font = Font(name="Segoe UI", bold=True, color="FFFFFF")
        header_fill = PatternFill("solid", fgColor="1F4E78")
        for ws in workbook.worksheets:
            ws.freeze_panes = "B2" if ws == sheet else "A2"
            for cell in ws[1]:
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = Alignment(horizontal="center")
            ws.auto_filter.ref = ws.dimensions
            for column in ws.columns:
                ws.column_dimensions[column[0].column_letter].width = min(
                    max(max(len(str(cell.value or "")) for cell in column) + 2, 12), 38
                )

        target_dir = output_dir or OUTPUT_DIR
        target_dir.mkdir(parents=True, exist_ok=True)
        filename = f"NIFTY200_RSI_Report_{report_end.isoformat()}_{datetime.now():%H%M%S}.xlsx"
        path = target_dir / filename
        workbook.save(path)
        return {
            "success": True,
            "file_path": str(path),
            "filename": filename,
            "latest_trade_date": format_date_iso(max(dates)),
            "trading_days": len(dates),
            "stocks": len(symbols),
        }
