"""Weekly Bollinger ranking for the NIFTY Total Market (750-stock) universe."""
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from app.services.data_normalizer import DataNormalizer
from app.services.nse_client import NSEClient


class WeeklyBollingerService:
    """Fetch the live NIFTY 750 universe, create weekly closes, and export ranks.

    The supplied NIFTY Total Market constituent workbook is the authoritative
    universe for this report. Weekly closes are calculated from daily exchange
    records as the last traded close in each Monday-Sunday week. No daily values
    are used as individual Bollinger observations.
    """

    UNIVERSE_FILE = Path(__file__).resolve().parents[2] / "data" / "ind_niftytotalmarket_list.xlsx"
    DEFAULT_PERIOD = 55
    DEFAULT_MULTIPLIER = 1.0
    MAX_CONCURRENT_REQUESTS = 8
    HISTORY_BUFFER_DAYS = 14

    @classmethod
    def fetch_stock_universe(cls) -> List[Dict[str, str]]:
        """Read the user-supplied NIFTY Total Market constituent workbook."""
        if not cls.UNIVERSE_FILE.exists():
            raise FileNotFoundError(f"NIFTY universe workbook is missing: {cls.UNIVERSE_FILE}")
        frame = pd.read_excel(cls.UNIVERSE_FILE)
        required = {"Company Name", "Symbol"}
        if not required.issubset(frame.columns):
            raise ValueError(f"Universe workbook must contain columns: {sorted(required)}")
        constituents: Dict[str, Dict[str, str]] = {}
        for row in frame.to_dict(orient="records"):
            stock = DataNormalizer.normalize_stock_metadata(row)
            if stock and stock["symbol"]:
                symbol = stock["symbol"]
                constituents[symbol] = {
                    "symbol": symbol,
                    "company_name": stock.get("company_name") or symbol,
                }
        if not constituents:
            raise ValueError("The supplied NIFTY universe workbook contains no stock symbols.")
        return [constituents[s] for s in sorted(constituents)]

    @staticmethod
    def latest_completed_week_end(as_of: Optional[date] = None) -> date:
        """Return the prior Friday; the current Monday-Sunday candle is excluded."""
        today = as_of or date.today()
        current_friday = today + timedelta(days=(4 - today.weekday()) % 7)
        return current_friday - timedelta(days=7)

    @staticmethod
    def weekly_closes_from_daily(daily: pd.DataFrame, through: date) -> pd.Series:
        """Turn normalized daily records into last-trading-close per week."""
        if daily is None or daily.empty:
            return pd.Series(dtype=float)
        records = DataNormalizer.normalize_price_dataframe(daily)
        if not records:
            return pd.Series(dtype=float)
        frame = pd.DataFrame(records)
        frame["trade_date"] = pd.to_datetime(frame["trade_date"])
        frame = frame[(frame["trade_date"].dt.date <= through) & frame["close_price"].notna()]
        if frame.empty:
            return pd.Series(dtype=float)
        frame = frame.sort_values("trade_date").set_index("trade_date")
        # W-SUN labels the whole Monday-Sunday trading week. Selecting the
        # final observed close handles Friday holidays and market closures.
        return frame["close_price"].resample("W-SUN").last().dropna()

    @staticmethod
    def align_completed_weeks(weekly: pd.Series, through: date, period: int) -> pd.Series:
        """Return the exact consecutive completed-week window ending at `through`."""
        if period < 1:
            raise ValueError("Period must be positive.")
        last_week_label = pd.Timestamp(through) + pd.Timedelta(days=6 - through.weekday())
        expected_weeks = pd.date_range(end=last_week_label, periods=period, freq="W-SUN")
        return weekly.reindex(expected_weeks)

    @staticmethod
    def calculate_bollinger(symbol: str, weekly_closes: Iterable[float], period: int = 55,
                            multiplier: float = 1.0) -> Dict[str, Any]:
        values = pd.Series(list(weekly_closes), dtype="float64").dropna()
        if period < 1 or multiplier < 0:
            raise ValueError("Period must be positive and multiplier cannot be negative.")
        if len(values) < period:
            raise ValueError(f"Insufficient completed weekly closes: {len(values)} of {period}.")
        values = values.iloc[-period:]
        mean = float(values.mean())
        deviation = float(np.sqrt(((values - mean) ** 2).sum() / period))
        return {
            "symbol": symbol,
            "latest_close": float(values.iloc[-1]),
            "middle_band": mean,
            "standard_deviation": deviation,
            "upper_band": mean + multiplier * deviation,
            "lower_band": mean - multiplier * deviation,
            "weeks_used": len(values),
        }

    @staticmethod
    def sort_results(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        ranked = sorted(results, key=lambda row: (-row["upper_band"], row["symbol"]))
        for rank, row in enumerate(ranked, 1):
            row["rank"] = rank
        return ranked

    @classmethod
    def calculate_universe(cls, universe: List[Dict[str, str]], period: int = DEFAULT_PERIOD,
                           multiplier: float = DEFAULT_MULTIPLIER,
                           as_of: Optional[date] = None,
                           history_fetcher: Optional[Callable] = None,
                           progress_callback: Optional[Callable] = None,
                           max_workers: int = MAX_CONCURRENT_REQUESTS) -> Dict[str, Any]:
        """Fetch histories concurrently; report per-symbol failures and progress."""
        through = cls.latest_completed_week_end(as_of)
        # Fetch the required calendar weeks plus two weeks of margin to ensure
        # the first expected weekly candle is covered. Extra candles are not
        # substituted for any missing week inside the calculation window.
        start = through - timedelta(days=period * 7 + cls.HISTORY_BUFFER_DAYS)
        fetch_history = history_fetcher or NSEClient.get_stock_historical_data

        def calculate_one(stock):
            symbol = stock["symbol"]
            try:
                daily = fetch_history(symbol, start, through)
                weekly = cls.weekly_closes_from_daily(daily, through)
                aligned = cls.align_completed_weeks(weekly, through, period)
                valid_count = int(aligned.notna().sum())
                if valid_count != period:
                    missing = [stamp.strftime("%Y-%m-%d") for stamp in aligned[aligned.isna()].index]
                    raise ValueError(
                        f"Only {valid_count} of {period} aligned completed weekly closes are valid; "
                        f"missing week labels: {', '.join(missing)}"
                    )
                row = cls.calculate_bollinger(symbol, aligned.tolist(), period, multiplier)
                row["company_name"] = stock.get("company_name", symbol)
                row["week_labels"] = [stamp.strftime("%Y-%m-%d") for stamp in aligned.index]
                row["weekly_closes"] = [float(value) for value in aligned.tolist()]
                return row, None
            except Exception as exc:
                return None, {"symbol": symbol, "company_name": stock.get("company_name", symbol),
                              "reason": str(exc)}

        results, unavailable = [], []
        if universe:
            worker_count = max(1, min(int(max_workers), len(universe)))
            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                futures = {executor.submit(calculate_one, stock): stock for stock in universe}
                for completed, future in enumerate(as_completed(futures), start=1):
                    row, failure = future.result()
                    if row:
                        results.append(row)
                    if failure:
                        unavailable.append(failure)
                    if progress_callback:
                        progress_callback(completed, len(universe), futures[future]["symbol"])
        return {"results": cls.sort_results(results), "unavailable": unavailable,
                "latest_week_end": through, "universe_count": len(universe),
                "period": period, "multiplier": multiplier,
                "history_start_date": start,
                "history_buffer_days": cls.HISTORY_BUFFER_DAYS}

    @staticmethod
    def build_excel_report(report: Dict[str, Any]) -> Dict[str, Any]:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Weekly Bollinger Ranking"
        sheet.append(["Rank", "Stock Symbol", "Latest Closing Price", "Middle Band",
                      "Standard Deviation", "Upper Band", "Lower Band"])
        for item in report["results"]:
            sheet.append([item["rank"], item["symbol"], item["latest_close"], item["middle_band"],
                          item["standard_deviation"], item["upper_band"], item["lower_band"]])
        missing = workbook.create_sheet("Unavailable Data")
        missing.append(["Stock Symbol", "Company Name", "Reason"])
        for item in report["unavailable"]:
            missing.append([item["symbol"], item["company_name"], item["reason"]])
        history = workbook.create_sheet("Weekly Closes")
        ranked_results = report["results"]
        symbols = [item["symbol"] for item in ranked_results]
        history.append(["Week Ending"] + symbols)
        if ranked_results:
            labels = ranked_results[0]["week_labels"]
            for week_index, label in enumerate(labels):
                history.append([label] + [item["weekly_closes"][week_index] for item in ranked_results])
        notes = workbook.create_sheet("Run Details")
        notes.append(["Setting", "Value"])
        for row in (("Latest completed weekly candle", report["latest_week_end"].isoformat()),
                    ("Universe source", "data/ind_niftytotalmarket_list.xlsx"),
                    ("Daily history request starts", report["history_start_date"].isoformat()),
                    ("History buffer (calendar days)", report["history_buffer_days"]),
                    ("Weekly close construction", "Last NSE trading-day close in each Monday-Sunday week"),
                    ("Weeks per calculation", report["period"]),
                    ("Population variance divisor", report["period"]),
                    ("Standard deviation multiplier", report["multiplier"]),
                    ("Universe stocks", report["universe_count"]),
                    ("Eligible stocks", len(report["results"])),
                    ("Unavailable stocks", len(report["unavailable"]))):
            notes.append(list(row))
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill("solid", fgColor="1F4E78")
        for ws in workbook.worksheets:
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
            for cell in ws[1]:
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = Alignment(horizontal="center")
            for column in ws.columns:
                ws.column_dimensions[column[0].column_letter].width = min(
                    max(max(len(str(cell.value or "")) for cell in column) + 2, 12), 60)
        for row in sheet.iter_rows(min_row=2, min_col=3, max_col=7):
            for cell in row:
                cell.number_format = "0.00"
        for row in history.iter_rows(min_row=2, min_col=2):
            for cell in row:
                cell.number_format = "0.00"
        buffer = BytesIO()
        workbook.save(buffer)
        filename = f"NIFTY750_Weekly_Bollinger_{report['latest_week_end']:%Y%m%d}.xlsx"
        return {"data": buffer.getvalue(), "filename": filename}
