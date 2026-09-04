import os
from pathlib import Path
from dotenv import load_dotenv
from app.utils.logger import logger

# Load environment variables from .env file at workspace root
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)
    logger.debug(f"Loaded environment variables from {ENV_PATH}")
else:
    load_dotenv()
    logger.warning(f".env file not found at {ENV_PATH}, relying on process environment variables.")

class Config:
    """Application Configuration Class"""
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: int = int(os.getenv("DB_PORT", 3306))
    DB_NAME: str = os.getenv("DB_NAME", "cnx200_rsi_dashboard")
    DB_USER: str = os.getenv("DB_USER", "root")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # Ingestion Configuration
    HISTORICAL_START_DATE: str = os.getenv("HISTORICAL_START_DATE", "")
    HISTORICAL_END_DATE: str = os.getenv("HISTORICAL_END_DATE", "")

    # Retry Configuration
    NSE_MAX_RETRIES: int = int(os.getenv("NSE_MAX_RETRIES", 3))
    NSE_RETRY_MIN_WAIT: int = int(os.getenv("NSE_RETRY_MIN_WAIT", 2))
    NSE_RETRY_MAX_WAIT: int = int(os.getenv("NSE_RETRY_MAX_WAIT", 10))

    @classmethod
    def get_database_url(cls, with_db: bool = True) -> str:
        """
        Constructs MySQL database connection URL.
        If with_db is False, returns server connection URL without target DB name.
        """
        # Escape password if special characters exist (basic safety)
        password_part = f":{cls.DB_PASSWORD}" if cls.DB_PASSWORD else ""
        user_part = f"{cls.DB_USER}{password_part}"
        host_part = f"{cls.DB_HOST}:{cls.DB_PORT}"
        
        if with_db:
            return f"mysql+pymysql://{user_part}@{host_part}/{cls.DB_NAME}?charset=utf8mb4"
        else:
            return f"mysql+pymysql://{user_part}@{host_part}/?charset=utf8mb4"

config = Config()
