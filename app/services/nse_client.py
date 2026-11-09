from io import BytesIO
from typing import Optional, Union
from datetime import date, datetime
import pandas as pd

from nselib import capital_market
from nselib.libutil import nse_urlfetch

from app.utils.logger import logger
from app.utils.retry import nse_retry
from app.utils.date_utils import format_date_nselib, parse_date

class NSEClient:
    """
    Central abstraction for all interactions with NSE India data via nselib.
    Isolates external nselib API dependency from the rest of the application.
    """

    NIFTY200_URL = "https://nsearchives.nseindia.com/content/indices/ind_nifty200list.csv"

    @staticmethod
    @nse_retry
    def get_trading_holiday_calendar() -> pd.DataFrame:
        """Fetch NSE's official holiday calendar for all market segments."""
        import nselib

        return nselib.trading_holiday_calendar()

    @staticmethod
    @nse_retry
    def get_nifty200_constituents() -> pd.DataFrame:
        """
        Fetches official NIFTY 200 constituent list from NSE.
        Returns DataFrame containing columns: ['Company Name', 'Industry', 'Symbol', 'Series', 'ISIN Code']
        """
        logger.info(f"Fetching official NIFTY 200 constituents from {NSEClient.NIFTY200_URL}...")
        response = nse_urlfetch(NSEClient.NIFTY200_URL)
        if response.status_code != 200:
            logger.error(f"Failed to fetch NIFTY 200 constituents from NSE. Status Code: {response.status_code}")
            raise ConnectionError(f"NSE returned HTTP {response.status_code} for NIFTY 200 list.")
            
        df = pd.read_csv(BytesIO(response.content))
        df.columns = [col.strip() for col in df.columns]
        logger.info(f"Successfully retrieved {len(df)} NIFTY 200 constituents.")
        return df

    @staticmethod
    @nse_retry
    def get_stock_historical_data(
        symbol: str,
        start_date: Union[str, date, datetime],
        end_date: Union[str, date, datetime]
    ) -> pd.DataFrame:
        """
        Fetches historical daily price and volume data for a specific stock symbol.
        Params:
            symbol: Stock ticker symbol (e.g. 'RELIANCE')
            start_date: Start date (string or date object)
            end_date: End date (string or date object)
        Returns:
            pandas DataFrame containing daily price records.
        """
        symbol_clean = symbol.strip().upper()
        from_str = format_date_nselib(start_date)
        to_str = format_date_nselib(end_date)

        logger.info(f"Fetching historical market data for {symbol_clean} from {from_str} to {to_str}...")
        df = capital_market.price_volume_and_deliverable_position_data(
            symbol=symbol_clean,
            from_date=from_str,
            to_date=to_str
        )
        if df is None or df.empty:
            logger.warning(f"No historical data returned for {symbol_clean} between {from_str} and {to_str}.")
            return pd.DataFrame()

        logger.info(f"Retrieved {len(df)} price records for {symbol_clean}.")
        return df

    @staticmethod
    @nse_retry
    def get_daily_market_data(trade_date: Union[str, date, datetime]) -> pd.DataFrame:
        """
        Fetches common CM Bhavcopy for all equities traded on a given date.
        Params:
            trade_date: Target trade date (string or date object)
        Returns:
            pandas DataFrame containing full market Bhavcopy.
        """
        date_str = format_date_nselib(trade_date)
        logger.info(f"Fetching NSE Bhavcopy for date {date_str}...")
        
        try:
            df = capital_market.bhav_copy_equities(trade_date=date_str)
            if df is None or df.empty:
                logger.warning(f"No Bhavcopy data returned for date {date_str}.")
                return pd.DataFrame()
            logger.info(f"Retrieved Bhavcopy with {len(df)} total market rows for date {date_str}.")
            return df
        except FileNotFoundError:
            # nselib currently maps both a genuine missing bhavcopy and NSE's
            # HTTP 403 response to FileNotFoundError. Keep this distinguishable
            # from an empty holiday response so callers can use the per-symbol
            # historical endpoint as a fallback.
            logger.warning(f"NSE Bhavcopy unavailable for {date_str}; it may be a holiday or an NSE 403.")
            raise ConnectionError(f"NSE Bhavcopy unavailable for {date_str} (holiday or HTTP 403).")
