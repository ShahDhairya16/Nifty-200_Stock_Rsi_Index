from datetime import date, datetime


def format_date(value):
    if not value:
        return "-"
    if isinstance(value, (date, datetime)):
        return value.strftime("%d-%b-%Y")
    return str(value)


def format_number(value, decimals=2):
    return "-" if value is None else f"{float(value):,.{decimals}f}"


def format_price(value):
    return "-" if value is None else f"₹{float(value):,.2f}"