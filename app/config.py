import os
from dotenv import load_dotenv

load_dotenv()


def get_secret(name: str, default=None):
    """Read Streamlit secrets first, then environment (including local .env)."""
    try:
        import streamlit as st

        value = st.secrets.get(name)
        if value is not None and value != "":
            return value
    except Exception:
        # Streamlit secrets are unavailable during local CLI use unless configured.
        pass
    return os.getenv(name, default)


class Config:
    """Configuration for the MongoDB-based NSE data pipeline."""

    MONGO_URI: str = get_secret("MONGO_URI", "mongodb://localhost:27017/")
    MONGO_DB_NAME: str = get_secret("MONGO_DB_NAME", "cnx200_rsi_dashboard")

    LOG_LEVEL: str = get_secret("LOG_LEVEL", "INFO")
    HISTORICAL_START_DATE: str = get_secret("HISTORICAL_START_DATE", "")
    HISTORICAL_END_DATE: str = get_secret("HISTORICAL_END_DATE", "")
    NSE_MAX_RETRIES: int = int(get_secret("NSE_MAX_RETRIES", 3))
    NSE_RETRY_MIN_WAIT: int = int(get_secret("NSE_RETRY_MIN_WAIT", 2))
    NSE_RETRY_MAX_WAIT: int = int(get_secret("NSE_RETRY_MAX_WAIT", 10))


config = Config()
