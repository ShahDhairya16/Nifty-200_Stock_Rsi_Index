"""Daily Bollinger calculations for the supplied NIFTY Total Market universe."""
from datetime import date, datetime, time, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import closing
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional
from zoneinfo import ZoneInfo
import hashlib
import json
import sqlite3

import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from nselib import capital_market

from app.services.data_normalizer import DataNormalizer
from app.utils.nse_trading_calendar import NSE_HOLIDAYS, NSE_SPECIAL_SESSIONS


@lru_cache(maxsize=400)
def _fetch_bhavcopy_cached(trade_date: date, symbol_series: tuple) -> Dict[str, float]:
    """Cache selected closes in memory and on disk to accelerate future refreshes."""
    universe_key = hashlib.sha256(
        json.dumps((2, symbol_series), separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    cache_path = WeeklyBollingerService.BHAVCOPY_CACHE_FILE
    try:
        with closing(sqlite3.connect(cache_path, timeout=30)) as connection:
            with connection:
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS daily_closes ("
                    "trade_date TEXT NOT NULL, universe_key TEXT NOT NULL, "
                    "closes_json TEXT NOT NULL, PRIMARY KEY (trade_date, universe_key))"
                )
                cached = connection.execute(
                    "SELECT closes_json FROM daily_closes WHERE trade_date=? AND universe_key=?",
                    (trade_date.isoformat(), universe_key),
                ).fetchone()
        if cached:
            cached_prices = {
                symbol: float(close) for symbol, close in json.loads(cached[0]).items()
            }
            if cached_prices:
                return cached_prices
    except (OSError, sqlite3.Error, json.JSONDecodeError):
        # Read-only or unavailable local storage should not prevent a live fetch.
        pass

    frame = capital_market.bhav_copy_equities(trade_date.strftime("%d-%m-%Y"))
    if frame is None or frame.empty:
        raise ValueError("NSE bhavcopy was empty")
    closes = WeeklyBollingerService._normalize_bhavcopy_day(
        frame, trade_date, dict(symbol_series)
    )
    if not closes:
        raise ValueError("NSE bhavcopy contained no requested-universe equity closes")
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(cache_path, timeout=30)) as connection:
            with connection:
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS daily_closes ("
                    "trade_date TEXT NOT NULL, universe_key TEXT NOT NULL, "
                    "closes_json TEXT NOT NULL, PRIMARY KEY (trade_date, universe_key))"
                )
                connection.execute(
                    "INSERT OR REPLACE INTO daily_closes "
                    "(trade_date, universe_key, closes_json) VALUES (?, ?, ?)",
                    (trade_date.isoformat(), universe_key, json.dumps(closes, separators=(",", ":"))),
                )
    except (OSError, sqlite3.Error, TypeError, ValueError):
        # The live result is still usable when persistent caching is unavailable.
        pass
    return closes


class WeeklyBollingerService:
    """Fetch daily NSE prices for the supplied NIFTY universe and export bands.

    The supplied NIFTY Total Market constituent workbook is the authoritative
    universe for this report. Each calculation uses the last 55 completed NSE
    trading-session closes, sourced from market-wide daily bhavcopy files.
    Stocks are ranked by how far the latest close is above (+) or below (-)
    the middle band, as a percentage of the middle band.
    """

    UNIVERSE_FILE = Path(__file__).resolve().parents[2] / "data" / "ind_niftytotalmarket_list.xlsx"
    BHAVCOPY_CACHE_FILE = Path(__file__).resolve().parents[2] / "data" / "nifty750_bhavcopy_cache.sqlite3"
    DEFAULT_PERIOD = 55
    DEFAULT_MULTIPLIER = 3.7
    # Stored with each snapshot so one made under an older ranking rule can be
    # recognised and re-ranked.
    RANKING_BASIS = "close_vs_middle_pct"
    # A bounded pool speeds up the cold fetch while keeping NSE request bursts
    # well below the requested 50–100 connection range that can trigger throttling.
    MAX_CONCURRENT_REQUESTS = 24
    MAX_LATEST_DATE_FALLBACK_SESSIONS = 10

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
                    "series": stock.get("series") or "EQ",
                }
        if not constituents:
            raise ValueError("The supplied NIFTY universe workbook contains no stock symbols.")
        return [constituents[s] for s in sorted(constituents)]

    @staticmethod
    def latest_completed_trade_date(as_of: Optional[date] = None,
                                    trading_session_checker: Optional[Callable] = None,
                                    now: Optional[datetime] = None) -> date:
        """Return the latest completed NSE session using India market time.

        On today's date, include today's close after the 15:30 IST cash-market
        close. Before then, use the prior completed trading session. Historical
        report dates are treated as completed dates, matching the NIFTY 200
        report end-date behavior.
        """
        if trading_session_checker is None:
            trading_session_checker = WeeklyBollingerService.is_nse_trading_session
        market_now = now or datetime.now(ZoneInfo("Asia/Kolkata"))
        if market_now.tzinfo is None:
            market_now = market_now.replace(tzinfo=ZoneInfo("Asia/Kolkata"))
        market_now = market_now.astimezone(ZoneInfo("Asia/Kolkata"))
        today = market_now.date()
        target = min(as_of or today, today)
        if target == today and market_now.time() < time(15, 30):
            target -= timedelta(days=1)
        while not trading_session_checker(target):
            target -= timedelta(days=1)
        return target

    @staticmethod
    def is_nse_trading_session(day: date) -> bool:
        """Use maintained 2025-26 holidays locally; consult NSE outside that range."""
        if day.year in {2025, 2026}:
            return day in NSE_SPECIAL_SESSIONS or (
                day.weekday() < 5 and day not in NSE_HOLIDAYS
            )
        from app.utils.nse_trading_calendar import is_nse_trading_session

        return is_nse_trading_session(day)

    @staticmethod
    def expected_trading_days(through: date, period: int,
                              trading_session_checker: Optional[Callable] = None) -> List[date]:
        """Return the latest exact number of NSE working-session dates."""
        if period < 1:
            raise ValueError("Period must be positive.")
        if trading_session_checker is None:
            trading_session_checker = WeeklyBollingerService.is_nse_trading_session
        dates = []
        cursor = through
        earliest_allowed = through - timedelta(days=max(366, period * 3))
        while len(dates) < period and cursor >= earliest_allowed:
            if trading_session_checker(cursor):
                dates.append(cursor)
            cursor -= timedelta(days=1)
        if len(dates) != period:
            raise ValueError(f"Could not identify {period} NSE trading sessions before {through}.")
        return sorted(dates)

    @classmethod
    def fetch_daily_market_closes(
        cls,
        universe: List[Dict[str, str]],
        through: date,
        period: int,
        progress_callback: Optional[Callable] = None,
        max_workers: int = MAX_CONCURRENT_REQUESTS,
        bhavcopy_fetcher: Optional[Callable] = None,
        trading_session_checker: Optional[Callable] = None,
    ) -> tuple:
        """Fetch one market-wide NSE bhavcopy for every requested session."""
        if trading_session_checker is None:
            trading_session_checker = cls.is_nse_trading_session

        dates = cls.expected_trading_days(through, period, trading_session_checker)

        symbols = {item["symbol"]: str(item.get("series") or "EQ").upper() for item in universe}
        symbol_series = tuple(sorted(symbols.items()))

        def fetch_one_day(session_date):
            for attempt in range(2):
                try:
                    if bhavcopy_fetcher is None:
                        prices = _fetch_bhavcopy_cached(session_date, symbol_series)
                    else:
                        daily = bhavcopy_fetcher(session_date)
                        if daily is None or daily.empty:
                            return session_date, {}, "NSE bhavcopy was empty"
                        prices = cls._normalize_bhavcopy_day(daily, session_date, symbols)
                    if not prices:
                        raise ValueError("NSE bhavcopy contained no requested-universe equity closes")
                    return session_date, prices, ""
                except Exception as exc:
                    if attempt == 1:
                        return session_date, {}, str(exc)

        daily_data = {}
        worker_count = max(1, min(int(max_workers), max(1, len(dates))))
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {executor.submit(fetch_one_day, trade_date): trade_date for trade_date in dates}
            for completed, future in enumerate(as_completed(futures), start=1):
                trade_date, closes, error = future.result()
                daily_data[trade_date] = (closes, error)
                if progress_callback:
                    progress_callback(completed, len(dates), trade_date.strftime("%Y-%m-%d"))
        return dates, daily_data

    @staticmethod
    def _normalize_bhavcopy_day(daily: pd.DataFrame, trade_date: date,
                                requested_symbols: Dict[str, str]) -> Dict[str, float]:
        """Normalize a whole exchange file with vectorized pandas operations."""
        normalized_columns = {
            DataNormalizer._clean_key(column): column for column in daily.columns
        }

        def find_column(aliases):
            for alias in aliases:
                column = normalized_columns.get(DataNormalizer._clean_key(alias))
                if column is not None:
                    return column
            return None

        symbol_col = find_column(DataNormalizer.SYMBOL_ALIASES)
        date_col = find_column(DataNormalizer.DATE_ALIASES)
        close_col = find_column(DataNormalizer.CLOSE_ALIASES)
        series_col = find_column(DataNormalizer.SERIES_ALIASES)
        if not symbol_col or not date_col or not close_col:
            raise ValueError("NSE bhavcopy is missing a symbol, trading date, or close column")

        symbols = daily[symbol_col].astype(str).str.strip().str.upper()
        mask = symbols.isin(requested_symbols)
        target_series = symbols.map(requested_symbols)
        series = None
        if series_col:
            series = daily[series_col].fillna("").astype(str).str.strip().str.upper()
            exact_series = series.eq(target_series)
            # NSE can move fully paid EQ shares into BE/BZ trade-to-trade
            # settlement. Those are still valid equity closes for the same
            # symbol and should be included in its price history.
            equity_trade_to_trade = target_series.eq("EQ") & series.isin({"BE", "BZ"})
            mask &= series.eq("") | exact_series | equity_trade_to_trade
        traded_dates = pd.to_datetime(daily[date_col], errors="coerce").dt.date
        mask &= traded_dates.eq(trade_date)
        if not mask.any():
            return {}

        closes = pd.to_numeric(
            daily.loc[mask, close_col].astype(str).str.replace(",", "", regex=False),
            errors="coerce",
        )
        selected_data = {"symbol": symbols[mask], "close": closes}
        if series is not None:
            selected_data["exact_series"] = series[mask].eq(target_series[mask])
        selected = pd.DataFrame(selected_data).dropna(subset=["close"])
        if "exact_series" in selected:
            selected = selected.sort_values("exact_series", ascending=False)
        selected = selected.drop_duplicates(subset=["symbol"], keep="first")
        return {str(row.symbol): float(row.close) for row in selected.itertuples(index=False)}

    @staticmethod
    def calculate_bollinger(symbol: str, closes: Iterable[float], period: int = 55,
                            multiplier: float = 3.7) -> Dict[str, Any]:
        values = pd.Series(list(closes), dtype="float64").dropna()
        if period < 1 or multiplier < 0:
            raise ValueError("Period must be positive and multiplier cannot be negative.")
        if len(values) < period:
            raise ValueError(f"Insufficient completed daily closes: {len(values)} of {period}.")
        values = values.iloc[-period:]
        mean = float(values.mean())
        deviation = float(np.sqrt(((values - mean) ** 2).sum() / period))
        latest_close = float(values.iloc[-1])
        return {
            "symbol": symbol,
            "latest_close": latest_close,
            "middle_band": mean,
            "standard_deviation": deviation,
            "upper_band": mean + multiplier * deviation,
            "lower_band": mean - multiplier * deviation,
            "close_vs_middle_pct": WeeklyBollingerService.percent_from_middle(latest_close, mean),
            "observations_used": len(values),
        }

    @staticmethod
    def percent_from_middle(latest_close: float, middle_band: float) -> Optional[float]:
        """Return how far the latest close is above (+) or below (-) the middle band, in percent."""
        if not middle_band:
            return None
        return (latest_close - middle_band) / middle_band * 100.0

    @staticmethod
    def sort_results(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Rank stocks by the latest close's percentage distance from the middle band.

        With a middle band of 100, a close of 150 (+50%) ranks above a close of
        130 (+30%), whatever the share price. Stocks below the middle band have
        negative values and rank after every stock above it.
        """
        for row in results:
            if row.get("close_vs_middle_pct") is None:
                row["close_vs_middle_pct"] = WeeklyBollingerService.percent_from_middle(
                    row["latest_close"], row["middle_band"]
                )
        ranked = sorted(results, key=lambda row: (
            row["close_vs_middle_pct"] is None,
            -(row["close_vs_middle_pct"] or 0.0),
            row["symbol"],
        ))
        for rank, row in enumerate(ranked, 1):
            row["rank"] = rank
        return ranked

    @classmethod
    def calculate_universe(cls, universe: List[Dict[str, str]], period: int = DEFAULT_PERIOD,
                           multiplier: float = DEFAULT_MULTIPLIER,
                           as_of: Optional[date] = None,
                           progress_callback: Optional[Callable] = None,
                           bhavcopy_fetcher: Optional[Callable] = None,
                           trading_session_checker: Optional[Callable] = None,
                           max_workers: int = MAX_CONCURRENT_REQUESTS) -> Dict[str, Any]:
        """Calculate bands from the same exact window of NSE trading sessions."""
        if period < 1:
            raise ValueError("Period must be positive.")
        through = cls.latest_completed_trade_date(as_of, trading_session_checker)
        for fallback_count in range(cls.MAX_LATEST_DATE_FALLBACK_SESSIONS + 1):
            dates, daily_market_data = cls.fetch_daily_market_closes(
                universe, through, period, progress_callback, max_workers,
                bhavcopy_fetcher=bhavcopy_fetcher,
                trading_session_checker=trading_session_checker,
            )
            newest_session_error = daily_market_data[dates[-1]][1]
            if not newest_session_error or fallback_count == cls.MAX_LATEST_DATE_FALLBACK_SESSIONS:
                break
            # Use one common, fully available market-file endpoint for every
            # stock. A missing newest bhavcopy should move the whole window back,
            # not mark every constituent as missing that date.
            through = dates[-1] - timedelta(days=1)
        results, unavailable = [], []
        daily_closes_by_symbol = {}
        global_errors = [
            f"{trade_date:%Y-%m-%d}: {daily_market_data[trade_date][1]}"
            for trade_date in dates if daily_market_data[trade_date][1]
        ]
        for stock in universe:
            symbol = stock["symbol"]
            values = [daily_market_data[trade_date][0].get(symbol, np.nan) for trade_date in dates]
            aligned = pd.Series(values, index=dates, dtype="float64")
            daily_closes_by_symbol[symbol] = [
                float(value) if pd.notna(value) else None for value in aligned.tolist()
            ]
            if aligned.notna().sum() != period:
                missing_dates = [
                    stamp.strftime("%Y-%m-%d")
                    for stamp in aligned[aligned.isna()].index
                ]
                reason = (
                    f"Only {int(aligned.notna().sum())} of {period} daily trading-session closes are valid; "
                    f"missing dates: {', '.join(missing_dates)}"
                )
                if global_errors:
                    reason += ". NSE file errors: " + "; ".join(global_errors)
                unavailable.append({
                    "symbol": symbol,
                    "company_name": stock.get("company_name", symbol),
                    "reason": reason,
                })
                continue
            row = cls.calculate_bollinger(symbol, aligned.tolist(), period, multiplier)
            row["company_name"] = stock.get("company_name", symbol)
            row["price_dates"] = [stamp.strftime("%Y-%m-%d") for stamp in aligned.index]
            row["daily_closes"] = [float(value) for value in aligned.tolist()]
            results.append(row)

        return {
            "results": cls.sort_results(results),
            "unavailable": unavailable,
            "price_dates": [stamp.strftime("%Y-%m-%d") for stamp in dates],
            "daily_closes_by_symbol": daily_closes_by_symbol,
            "latest_trade_date": dates[-1],
            "universe_count": len(universe),
            "period": period,
            "multiplier": multiplier,
            "history_start_date": dates[0],
            "price_data_source": "NSE market-wide daily bhavcopy",
            "ranking_basis": cls.RANKING_BASIS,
        }

    @staticmethod
    def build_excel_report(report: Dict[str, Any]) -> Dict[str, Any]:
        workbook = Workbook()
        history = workbook.active
        history.title = "Daily Closing Prices"
        symbols = sorted(report.get("daily_closes_by_symbol", {}))
        history.append(["Trading Date"] + symbols)
        for day_index, label in enumerate(report.get("price_dates", [])):
            history.append([label] + [
                report["daily_closes_by_symbol"][symbol][day_index]
                for symbol in symbols
            ])

        sheet = workbook.create_sheet("Bollinger Ranking")
        sheet.append(["Rank", "Stock Symbol", "Latest Closing Price", "Middle Band",
                      "% vs Middle Band", "Standard Deviation", "Upper Band", "Lower Band",
                      "Observations Used"])
        for item in report["results"]:
            percent = item.get("close_vs_middle_pct")
            # Excel percentage cells hold fractions: 0.5 is shown as +50.00%.
            sheet.append([item["rank"], item["symbol"], item["latest_close"], item["middle_band"],
                          percent / 100 if percent is not None else None,
                          item["standard_deviation"], item["upper_band"], item["lower_band"],
                          item["observations_used"]])
        missing = workbook.create_sheet("Unavailable Data")
        missing.append(["Stock Symbol", "Company Name", "Reason"])
        for item in report["unavailable"]:
            missing.append([item["symbol"], item["company_name"], item["reason"]])
        notes = workbook.create_sheet("Run Details")
        notes.append(["Setting", "Value"])
        for row in (("Latest completed trading session", report["latest_trade_date"].isoformat()),
                    ("Universe source", "data/ind_niftytotalmarket_list.xlsx"),
                    ("Earliest trading session in calculation", report["history_start_date"].isoformat()),
                    ("Price data source", report["price_data_source"]),
                    ("Close construction", "Available daily closes for all universe stocks; missing sessions are blank and are not forward-filled"),
                    ("Closing-price sheet", "Contains partial history even for stocks omitted from the 55-session ranking"),
                    ("Trading sessions per calculation", report["period"]),
                    ("Population variance divisor", report["period"]),
                    ("Standard deviation multiplier", report["multiplier"]),
                    ("Ranking", "Highest % vs Middle Band first: (Latest Closing Price - Middle Band) / Middle Band"),
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
        for row in sheet.iter_rows(min_row=2, min_col=3, max_col=8):
            for cell in row:
                cell.number_format = "0.00"
        for row in sheet.iter_rows(min_row=2, min_col=5, max_col=5):
            for cell in row:
                cell.number_format = "+0.00%;-0.00%;0.00%"
        for row in history.iter_rows(min_row=2, min_col=2):
            for cell in row:
                cell.number_format = "0.00"
        buffer = BytesIO()
        workbook.save(buffer)
        filename = f"NIFTY750_Daily_Bollinger_{report['latest_trade_date']:%Y%m%d}.xlsx"
        return {"data": buffer.getvalue(), "filename": filename}
