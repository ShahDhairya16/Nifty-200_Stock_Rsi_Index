import os


class Config:
    """Configuration for the file-based NSE data pipeline."""

    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    HISTORICAL_START_DATE: str = os.getenv("HISTORICAL_START_DATE", "")
    HISTORICAL_END_DATE: str = os.getenv("HISTORICAL_END_DATE", "")
    NSE_MAX_RETRIES: int = int(os.getenv("NSE_MAX_RETRIES", 3))
    NSE_RETRY_MIN_WAIT: int = int(os.getenv("NSE_RETRY_MIN_WAIT", 2))
    NSE_RETRY_MAX_WAIT: int = int(os.getenv("NSE_RETRY_MAX_WAIT", 10))


config = Config()
