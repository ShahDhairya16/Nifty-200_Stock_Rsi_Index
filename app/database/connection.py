from typing import Optional
from pymongo import MongoClient
from pymongo.database import Database
from app.config import config
from app.utils.logger import logger

_client: Optional[MongoClient] = None


def get_mongo_client() -> MongoClient:
    """Creates or retrieves the singleton PyMongo MongoClient instance."""
    global _client
    if _client is None:
        try:
            _client = MongoClient(
                config.MONGO_URI,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000,
                maxPoolSize=50,
                minPoolSize=5,
            )
            logger.info(f"MongoDB client initialized for URI: {config.MONGO_URI}")
        except Exception as e:
            logger.error(f"Failed to initialize MongoDB client: {e}")
            raise
    return _client


def get_database(db_name: Optional[str] = None) -> Database:
    """Returns the target MongoDB database."""
    client = get_mongo_client()
    target_db = db_name or config.MONGO_DB_NAME
    return client[target_db]


def check_db_connection() -> bool:
    """Tests connectivity to the MongoDB server."""
    try:
        client = get_mongo_client()
        client.admin.command("ping")
        logger.info(f"MongoDB connection test successful on target '{config.MONGO_DB_NAME}'.")
        return True
    except Exception as e:
        logger.error(f"MongoDB connection check failed: {e}")
        return False


def close_connection() -> None:
    """Closes the MongoDB client connection if open."""
    global _client
    if _client is not None:
        _client.close()
        _client = None
        logger.info("MongoDB client connection closed.")
