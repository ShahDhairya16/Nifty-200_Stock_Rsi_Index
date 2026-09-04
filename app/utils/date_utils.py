from datetime import date, datetime, timedelta
from typing import Union, List, Optional
from app.utils.logger import logger

DATE_FORMATS = [
    "%Y-%m-%d",
    "%d-%m-%Y",
    "%d-%b-%Y",
    "%Y/%m/%d",
    "%d/%m/%Y"
]

def parse_date(date_val: Union[str, date, datetime]) -> Optional[date]:
    """
    Parses a string, date, or datetime object into a Python date object.
    Supports multiple date formats (ISO, DD-MM-YYYY, DD-MMM-YYYY).
    """
    if date_val is None:
        return None
    if isinstance(date_val, date) and not isinstance(date_val, datetime):
        return date_val
    if isinstance(date_val, datetime):
        return date_val.date()
    
    date_str = str(date_val).strip()
    if not date_str or date_str in ("-", "NaN", "None", "null"):
        return None
    
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
            
    logger.warning(f"Could not parse date string: '{date_str}'")
    return None

def format_date_nselib(d: Union[str, date, datetime]) -> str:
    """
    Formats a date object into nselib required string format: DD-MM-YYYY.
    """
    parsed = parse_date(d)
    if not parsed:
        raise ValueError(f"Invalid date for nselib formatting: {d}")
    return parsed.strftime("%d-%m-%Y")

def format_date_iso(d: Union[str, date, datetime]) -> str:
    """
    Formats a date object into ISO standard string format: YYYY-MM-DD.
    """
    parsed = parse_date(d)
    if not parsed:
        raise ValueError(f"Invalid date for ISO formatting: {d}")
    return parsed.strftime("%Y-%m-%d")

def get_default_start_date(years_back: int = 1) -> date:
    """
    Returns default historical start date (default: 1 year prior to today).
    """
    today = date.today()
    try:
        return today.replace(year=today.year - years_back)
    except ValueError:
        # Handle leap year edge cases (e.g. Feb 29)
        return today - timedelta(days=365 * years_back)

def is_weekend(d: Union[str, date, datetime]) -> bool:
    """
    Checks if a given date is a weekend (Saturday or Sunday).
    """
    parsed = parse_date(d)
    if not parsed:
        return False
    return parsed.weekday() >= 5  # 5 = Saturday, 6 = Sunday

def get_date_range(start_date: date, end_date: date) -> List[date]:
    """
    Returns list of dates between start_date and end_date inclusive.
    """
    if start_date > end_date:
        return []
    delta = (end_date - start_date).days
    return [start_date + timedelta(days=i) for i in range(delta + 1)]
