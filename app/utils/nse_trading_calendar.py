"""NSE cash-market calendar backed by NSE's official holiday feed.

The exchange holiday API lists closures, not a complete schedule of exceptional
sessions. Muhurat sessions are identified from NSE's Diwali/Laxmi Pujan entries;
other announced special sessions can be registered in ``NSE_SPECIAL_SESSIONS``.
The official feed is cached for 24 hours, with the maintained calendar below as
an offline fallback.
"""
from datetime import date, datetime, timedelta, timezone
from typing import Optional, Set, Tuple

from app.utils.date_utils import parse_date
from app.utils.logger import logger


# NSE official 2026 cash-market holiday calendar (CM segment).
NSE_HOLIDAYS: Set[date] = {
    date(2026, 1, 15), date(2026, 1, 26), date(2026, 2, 15),
    date(2026, 2, 19), date(2026, 3, 3), date(2026, 3, 19),
    date(2026, 3, 21),
    date(2026, 3, 26), date(2026, 3, 31), date(2026, 4, 1),
    date(2026, 4, 3), date(2026, 4, 14), date(2026, 5, 1),
    date(2026, 5, 28), date(2026, 6, 26), date(2026, 8, 15),
    date(2026, 8, 26),
    date(2026, 9, 14), date(2026, 10, 2), date(2026, 10, 20),
    date(2026, 11, 8), date(2026, 11, 10), date(2026, 11, 24),
    date(2026, 12, 25),
}

# Official sessions outside normal weekday hours/days that aren't discoverable
# from the holiday feed description.
NSE_SPECIAL_SESSIONS: Set[date] = {date(2026, 11, 8)}

_CACHE_TTL = timedelta(hours=24)
_cached_at: Optional[datetime] = None
_cached_holidays: Set[date] = set()
_cached_special_sessions: Set[date] = set()


def _segment_is_cash_market(value: object) -> bool:
    segment = str(value or "").strip().upper()
    return segment in {"CM", "EQUITIES", "EQUITY", "CASH MARKET"}


def _load_official_calendar() -> Tuple[Set[date], Set[date]]:
    """Fetch and parse NSE's official calendar, retaining only cash-market rows."""
    # Lazy import keeps parsing the calendar independent from the NSE client.
    from app.services.nse_client import NSEClient

    frame = NSEClient.get_trading_holiday_calendar()
    if frame is None or frame.empty:
        raise ValueError("NSE returned an empty trading holiday calendar")

    columns = {str(column).strip().lower(): column for column in frame.columns}
    segment_column = columns.get("product") or columns.get("segment")
    date_column = columns.get("tradingdate") or columns.get("trading_date")
    description_column = columns.get("description")
    if date_column is None:
        raise ValueError("NSE trading holiday calendar has no tradingDate column")

    holidays: Set[date] = set()
    special_sessions: Set[date] = set()
    for _, row in frame.iterrows():
        if segment_column is not None and not _segment_is_cash_market(row[segment_column]):
            continue
        holiday_date = parse_date(row[date_column])
        if holiday_date is None:
            continue
        holidays.add(holiday_date)
        description = str(row[description_column] or "").lower() if description_column else ""
        if "muhurat" in description or "diwali laxmi pujan" in description:
            special_sessions.add(holiday_date)

    if not holidays:
        raise ValueError("NSE trading holiday calendar had no parseable cash-market dates")
    return holidays, special_sessions


def _get_calendar_dates() -> Tuple[Set[date], Set[date]]:
    global _cached_at, _cached_holidays, _cached_special_sessions
    now = datetime.now(timezone.utc)
    if _cached_at is not None and now - _cached_at < _CACHE_TTL:
        return _cached_holidays, _cached_special_sessions

    try:
        holidays, special_sessions = _load_official_calendar()
        _cached_holidays = holidays
        _cached_special_sessions = special_sessions
        logger.info("NSE trading calendar: refreshed cash-market holidays from NSE.")
    except Exception as exc:
        # Fallback is deliberately explicit in logs; it cannot silently imply
        # that a current NSE holiday feed was consulted.
        _cached_holidays = set(NSE_HOLIDAYS)
        _cached_special_sessions = set()
        logger.warning(f"NSE trading calendar: official calendar unavailable ({exc}); using maintained fallback dates.")
    _cached_at = now
    return _cached_holidays, _cached_special_sessions


def is_nse_trading_session(day: date) -> bool:
    """Return whether ``day`` is an NSE cash-market session.

    Weekends are closed unless an official Muhurat entry or a maintained
    exceptional session declares trading. Weekdays listed by NSE are closed.
    """
    holidays, feed_special_sessions = _get_calendar_dates()
    if day in NSE_SPECIAL_SESSIONS or day in feed_special_sessions:
        return True
    return day.weekday() < 5 and day not in holidays
