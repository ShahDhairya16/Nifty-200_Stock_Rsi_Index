import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Configuration for the MongoDB-based NSE data pipeline."""

    MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
    MONGO_DB_NAME: str = os.getenv("MONGO_DB_NAME", "cnx200_rsi_dashboard")

    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    HISTORICAL_START_DATE: str = os.getenv("HISTORICAL_START_DATE", "")
    HISTORICAL_END_DATE: str = os.getenv("HISTORICAL_END_DATE", "")
    NSE_MAX_RETRIES: int = int(os.getenv("NSE_MAX_RETRIES", 3))
    NSE_RETRY_MIN_WAIT: int = int(os.getenv("NSE_RETRY_MIN_WAIT", 2))
    NSE_RETRY_MAX_WAIT: int = int(os.getenv("NSE_RETRY_MAX_WAIT", 10))


config = Config()
