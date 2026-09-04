import os
from datetime import datetime, date
from pathlib import Path
from typing import Dict, Any, List, Optional
import pandas as pd
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from app.database.connection import get_db_session
from app.database.repositories import (
    StockRepository,
    DailyPriceRepository,
    RSIMetricsRepository
)
from app.services.ingestion_service import IngestionService
from app.services.rsi_service import RSIService
from app.utils.date_utils import format_date_iso
from app.utils.logger import logger

BASE_DIR = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = BASE_DIR / "output"

class ExcelReportService:
    """
    Service to generate formatted, real-time Excel reports containing:
    1. Last 70 trading days of closing prices for all active NIFTY 200 stocks.
    2. Latest RSI 22, 44, 66 & Average RSI rankings sorted descending.
    """

    @staticmethod
    def generate_nifty200_excel_report(
        output_dir: Optional[Path] = None,
        refresh_market_data: bool = True
    ) -> Dict[str, Any]:
        """
        Orchestrates market freshness check, RSI recalculation, and Excel file generation.
        Returns report summary dictionary.
        """
        logger.info("Starting NIFTY 200 Excel Report Generation...")

        # 1. Trigger Data Freshness Check & Ingestion
        with get_db_session() as session:
            latest_price_date = DailyPriceRepository.get_latest_price_date(session)
            # Check if any active stock has RSI for latest price date
            sample_stock = StockRepository.get_all_active_stocks(session)
            latest_rsi_metric = RSIMetricsRepository.get_latest_rsi_metric(session, sample_stock[0].id) if sample_stock else None
            latest_rsi_date = latest_rsi_metric.trade_date if latest_rsi_metric else None

        today = date.today()
        # If latest market price date has no RSI metrics computed yet, update database and calculate RSI
        if refresh_market_data and (not latest_price_date or latest_rsi_date != latest_price_date):
            logger.info("Market data or RSI metrics need updating. Running ingestion & RSI calculation...")
            try:
                IngestionService.update_missing_market_data()
                RSIService.compute_all_active_stocks_rsi()
            except Exception as e:
                logger.warning(f"Market data update warning: {e}")
        else:
            logger.info(f"Database market data & RSI metrics are up-to-date (Latest Market Date: {latest_price_date}). Skipping re-fetch.")

        # 2. Retrieve Database Data
        with get_db_session() as session:
            # Get latest 70 distinct trading dates
            trading_dates = DailyPriceRepository.get_last_n_trading_days(session, n=70)
            if not trading_dates:
                raise ValueError("No trading dates found in daily_prices. Please run data ingestion first.")

            latest_trade_date = trading_dates[-1]

            # Get active stock symbols
            active_stocks = StockRepository.get_all_active_stocks(session)
            active_symbols = [s.symbol for s in active_stocks]

            # Get bulk closing price matrix data
            matrix_data = DailyPriceRepository.get_closing_price_matrix_data(session, trading_dates)

            # Get latest RSI rankings
            rsi_rankings = RSIMetricsRepository.get_latest_rsi_rankings(session)

        # 3. Pivot Closing Price Matrix into DataFrame
        if matrix_data:
            df_matrix_raw = pd.DataFrame(matrix_data)
            df_pivot = df_matrix_raw.pivot(index="trade_date", columns="symbol", values="close_price")
            # Ensure all active symbols are present as columns
            for sym in active_symbols:
                if sym not in df_pivot.columns:
                    df_pivot[sym] = None
            # Reorder columns: Date first, then sorted active symbols
            df_pivot = df_pivot[sorted(active_symbols)].reset_index()
        else:
            df_pivot = pd.DataFrame(columns=["trade_date"] + sorted(active_symbols))

        # 4. Prepare RSI Ranking DataFrame
        rsi_rows = []
        for rank_idx, r in enumerate(rsi_rankings, 1):
            rsi_rows.append({
                "Rank": rank_idx,
                "Symbol": r["symbol"],
                "Company Name": r["company_name"],
                "Latest Date": r["trade_date"].strftime("%Y-%m-%d") if isinstance(r["trade_date"], (date, datetime)) else str(r["trade_date"]),
                "RSI 22": r["rsi_22"],
                "RSI 44": r["rsi_44"],
                "RSI 66": r["rsi_66"],
                "Average RSI": r["average_rsi"]
            })

        # 5. Build openpyxl Workbook
        wb = openpyxl.Workbook()
        
        # Styles
        header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
        border_side = Side(style="thin", color="D9D9D9")
        thin_border = Border(left=border_side, right=border_side, top=border_side, bottom=border_side)
        center_align = Alignment(horizontal="center", vertical="center")
        right_align = Alignment(horizontal="right", vertical="center")
        left_align = Alignment(horizontal="left", vertical="center")

        # ----------------------------------------------------
        # SHEET 1: Last 70 Days Closing Price
        # ----------------------------------------------------
        ws1 = wb.active
        ws1.title = "Last 70 Days Closing Price"

        # Headers
        ws1_headers = ["Date"] + list(df_pivot.columns[1:])
        ws1.append(ws1_headers)

        for col_num in range(1, len(ws1_headers) + 1):
            cell = ws1.cell(row=1, column=col_num)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = center_align

        # Rows
        for _, row in df_pivot.iterrows():
            row_vals = []
            t_date = row["trade_date"]
            date_str = t_date.strftime("%d-%b-%Y") if isinstance(t_date, (date, datetime)) else str(t_date)
            row_vals.append(date_str)

            for col_name in ws1_headers[1:]:
                val = row[col_name]
                row_vals.append(float(val) if val is not None and not pd.isna(val) else None)

            ws1.append(row_vals)

        # Formatting Sheet 1
        ws1.freeze_panes = "B2"  # Freeze top row and first column
        ws1.auto_filter.ref = ws1.dimensions

        for r in range(2, ws1.max_row + 1):
            date_cell = ws1.cell(row=r, column=1)
            date_cell.alignment = center_align
            date_cell.border = thin_border

            for c in range(2, ws1.max_column + 1):
                cell = ws1.cell(row=r, column=c)
                cell.border = thin_border
                cell.alignment = right_align
                if cell.value is not None:
                    cell.number_format = "#,##0.00"

        # Column widths for Sheet 1
        ws1.column_dimensions["A"].width = 15
        for c in range(2, ws1.max_column + 1):
            col_letter = get_column_letter(c)
            ws1.column_dimensions[col_letter].width = 14

        # ----------------------------------------------------
        # SHEET 2: RSI Ranking
        # ----------------------------------------------------
        ws2 = wb.create_sheet(title="RSI Ranking")
        ws2_headers = ["Rank", "Symbol", "Company Name", "Latest Date", "RSI 22", "RSI 44", "RSI 66", "Average RSI"]
        ws2.append(ws2_headers)

        for col_num in range(1, len(ws2_headers) + 1):
            cell = ws2.cell(row=1, column=col_num)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = center_align

        for r_dict in rsi_rows:
            ws2.append([
                r_dict["Rank"],
                r_dict["Symbol"],
                r_dict["Company Name"],
                r_dict["Latest Date"],
                r_dict["RSI 22"],
                r_dict["RSI 44"],
                r_dict["RSI 66"],
                r_dict["Average RSI"]
            ])

        # Formatting Sheet 2
        ws2.freeze_panes = "A2"
        ws2.auto_filter.ref = ws2.dimensions

        for r in range(2, ws2.max_row + 1):
            # Rank
            c_rank = ws2.cell(row=r, column=1)
            c_rank.alignment = center_align
            c_rank.number_format = "0"
            c_rank.border = thin_border

            # Symbol
            c_sym = ws2.cell(row=r, column=2)
            c_sym.alignment = left_align
            c_sym.border = thin_border

            # Company Name
            c_comp = ws2.cell(row=r, column=3)
            c_comp.alignment = left_align
            c_comp.border = thin_border

            # Date
            c_date = ws2.cell(row=r, column=4)
            c_date.alignment = center_align
            c_date.border = thin_border

            # RSI columns (5, 6, 7, 8)
            for c in range(5, 9):
                cell = ws2.cell(row=r, column=c)
                cell.border = thin_border
                cell.alignment = right_align
                if cell.value is not None:
                    cell.number_format = "0.00"

        # Column widths for Sheet 2
        ws2.column_dimensions["A"].width = 10
        ws2.column_dimensions["B"].width = 16
        ws2.column_dimensions["C"].width = 38
        ws2.column_dimensions["D"].width = 15
        ws2.column_dimensions["E"].width = 14
        ws2.column_dimensions["F"].width = 14
        ws2.column_dimensions["G"].width = 14
        ws2.column_dimensions["H"].width = 16

        # 6. Save Excel File
        target_dir = output_dir or OUTPUT_DIR
        target_dir.mkdir(parents=True, exist_ok=True)

        timestamp_str = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        filename = f"NIFTY200_RSI_Report_{timestamp_str}.xlsx"
        file_path = target_dir / filename

        wb.save(file_path)
        logger.info(f"Excel report successfully generated at {file_path}")

        return {
            "success": True,
            "file_path": str(file_path),
            "filename": filename,
            "latest_trade_date": format_date_iso(latest_trade_date),
            "trading_days": len(trading_dates),
            "stocks": len(active_symbols)
        }
