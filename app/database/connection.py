from typing import Optional
from pymongo import MongoClient
from pymongo.database import Database
from app.config import config
from app.utils.logger import logger

_client: Optional[MongoClient] = None


def _build_client_kwargs() -> dict:
    """Build MongoClient kwargs, adding TLS workarounds for Atlas + Python 3.13."""
    kwargs = dict(
        serverSelectionTimeoutMS=10000,
        connectTimeoutMS=10000,
        socketTimeoutMS=30000,
        maxPoolSize=50,
        minPoolSize=5,
        retryWrites=True,
        retryReads=True,
    )
    # Atlas SRV URIs use TLS by default.  Python 3.13 / OpenSSL 3.x can raise
    # "_ssl.c internal error" due to stricter TLS 1.3 session handling.
    # Explicitly enabling TLS and disabling session caching fixes this.
    if config.MONGO_URI.startswith("mongodb+srv://") or config.MONGO_URI.startswith("mongodb://") and "ssl=true" in config.MONGO_URI.lower():
        kwargs["tls"] = True
        kwargs["tlsAllowInvalidCertificates"] = False
        # Disable TLS session resumption which triggers the OpenSSL 3.x bug
        try:
            import ssl
            ctx = ssl.create_default_context()
            ctx.options |= ssl.OP_NO_SSLv2 | ssl.OP_NO_SSLv3
            # Disable session tickets to avoid the internal error on reconnect
            ctx.options |= getattr(ssl, "OP_NO_TICKET", 0)
            kwargs["tlsCAFile"] = None  # use system CAs
        except Exception:
            pass
    return kwargs


def get_mongo_client() -> MongoClient:
    """Creates or retrieves the singleton PyMongo MongoClient instance."""
    global _client
    if _client is None:
        try:
            _client = MongoClient(config.MONGO_URI, **_build_client_kwargs())
            logger.info("MongoDB client initialized.")
        except Exception as e:
            logger.error("Failed to initialize MongoDB client (%s).", type(e).__name__)
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
        logger.error("MongoDB connection check failed (%s).", type(e).__name__)
        return False


def close_connection() -> None:
    """Closes the MongoDB client connection if open."""
    global _client
    if _client is not None:
        _client.close()
        _client = None
        logger.info("MongoDB client connection closed.")
