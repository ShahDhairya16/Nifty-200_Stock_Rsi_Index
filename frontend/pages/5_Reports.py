import hashlib
import importlib
import json
import sys
from io import BytesIO
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from datetime import date
import streamlit as st
from frontend.components.sidebar import render_sidebar
from app.database import repositories as repositories_module
from app.services import data_normalizer as data_normalizer_module
from app.services import excel_report_service as excel_report_module
from app.services import stock_universe_service as stock_universe_module

STOCK_LIST_PATH = ROOT / "data" / "stocks.json"
REPORT_SOURCE_SIGNATURE = hashlib.sha256(
    b"pinned-nifty200-report-v3-validated-export:" + STOCK_LIST_PATH.read_bytes()
).hexdigest()


class ReportUniverseMismatch(Exception):
    """The generated workbook does not use the pinned NIFTY 200 universe."""


render_sidebar()
st.title("Reports")
st.caption(
    "Generate the last 70 trading days and RSI ranking. "
    "Both sheets use the pinned NIFTY 200 constituent list from 15-Oct-2026."
)

# Streamlit can preserve session_state across source updates. Discard reports
# created before this report implementation or against a different universe.
if (
    st.session_state.get("latest_report")
    and st.session_state.get("latest_report_source_signature") != REPORT_SOURCE_SIGNATURE
):
    st.session_state.pop("latest_report", None)
    st.session_state.pop("latest_report_source_signature", None)
    st.info(
        "A previous report used an older stock list and was cleared. "
        "Generate a fresh report to download the corrected workbook."
    )

report_date = st.date_input(
    "Report end date",
    value=date.today(),
    max_value=date.today(),
    help="The workbook includes the 70 trading days ending on or before this date."
)

if st.button("Generate Excel Report", type="primary"):
    # Never leave an earlier workbook available if this generation fails.
    st.session_state.pop("latest_report", None)
    st.session_state.pop("latest_report_source_signature", None)
    try:
        with st.spinner("Generating latest Excel report..."):
            # Streamlit Cloud can preserve imported Python modules after it
            # pulls a new repository revision. Reload this dependency chain so
            # the export uses the deployed pinned-universe implementation.
            importlib.reload(data_normalizer_module)
            importlib.reload(repositories_module)
            importlib.reload(stock_universe_module)
            excel_report_module = importlib.reload(excel_report_module)

            result = excel_report_module.ExcelReportService.generate_nifty200_excel_report(
                refresh_market_data=False,
                end_date=report_date,
                in_memory=True,
            )

        with STOCK_LIST_PATH.open("r", encoding="utf-8") as handle:
            expected_symbols = {
                str(stock["symbol"]).strip().upper()
                for stock in json.load(handle)
            }

        workbook = openpyxl.load_workbook(
            BytesIO(result["data"]), read_only=True, data_only=True
        )
        try:
            price_sheet = workbook["Last 70 Days Closing Price"]
            price_symbols = {
                str(cell.value).strip().upper()
                for cell in price_sheet[1][1:]
                if cell.value
            }

            ranking_sheet = workbook["RSI Ranking"]
            ranking_headers = [cell.value for cell in ranking_sheet[1]]
            symbol_column = ranking_headers.index("Symbol")
            ranking_symbols = {
                str(row[symbol_column]).strip().upper()
                for row in ranking_sheet.iter_rows(min_row=2, values_only=True)
                if row[symbol_column]
            }
        finally:
            workbook.close()

        if len(expected_symbols) != 200:
            raise ReportUniverseMismatch(
                f"Pinned stock list should contain 200 unique symbols; found {len(expected_symbols)}."
            )

        if price_symbols != expected_symbols or ranking_symbols != expected_symbols:
            missing_price = sorted(expected_symbols - price_symbols)
            extra_price = sorted(price_symbols - expected_symbols)
            missing_ranking = sorted(expected_symbols - ranking_symbols)
            extra_ranking = sorted(ranking_symbols - expected_symbols)
            raise ReportUniverseMismatch(
                "Generated report does not match the pinned NIFTY 200 list. "
                f"Closing-price sheet missing: {missing_price}; extra: {extra_price}. "
                f"RSI sheet missing: {missing_ranking}; extra: {extra_ranking}."
            )

        st.session_state["latest_report"] = result
        st.session_state["latest_report_source_signature"] = REPORT_SOURCE_SIGNATURE
        st.success(f"Report generated for {result['latest_trade_date']}.")
    except ReportUniverseMismatch as exc:
        st.error(str(exc))
    except Exception:
        st.error("Excel report generation failed. Check the MongoDB settings and confirm that market data is available.")

result = st.session_state.get("latest_report")
if result and result.get("data"):
    st.download_button("Download Excel Report", data=result["data"],
                       file_name=result["filename"],
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.caption(f"{result['trading_days']} trading days | {result['stocks']} stocks")
