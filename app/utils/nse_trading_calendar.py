"""Central NSE cash-market session calendar.

Update the year-specific holiday and special-session sets when NSE publishes
its annual circulars or announces additional sessions. Weekdays are sessions
unless listed as holidays; weekends are sessions only when explicitly listed.
"""
from datetime import date
from typing import Set


# NSE cash-market holidays notified for 2026 (NSE circular NSE/FAOP/71777).
NSE_HOLIDAYS: Set[date] = {
    date(2026, 1, 26), date(2026, 3, 3), date(2026, 3, 26),
    date(2026, 3, 31), date(2026, 4, 3), date(2026, 4, 14),
    date(2026, 5, 1), date(2026, 5, 28), date(2026, 6, 26),
    date(2026, 9, 14), date(2026, 10, 2), date(2026, 10, 20),
    date(2026, 11, 10), date(2026, 11, 24), date(2026, 12, 25),
}

# Keep official sessions outside normal weekday schedules here.
NSE_SPECIAL_SESSIONS: Set[date] = {date(2026, 11, 8)}


def is_nse_trading_session(day: date) -> bool:
    """Return whether NSE scheduled a cash-market session on ``day``."""
    if day in NSE_SPECIAL_SESSIONS:
        return True
    return day.weekday() < 5 and day not in NSE_HOLIDAYS
