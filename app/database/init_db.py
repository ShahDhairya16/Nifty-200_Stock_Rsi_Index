from pymongo import ASCENDING, DESCENDING
from app.config import config
from app.database.connection import get_database, check_db_connection
from app.utils.logger import logger


def init_database() -> bool:
    """
    Initializes MongoDB collections and creates optimized indexes.
    Safe to execute multiple times (idempotent).
    """
    try:
        logger.info(f"Connecting to MongoDB database '{config.MONGO_DB_NAME}'...")
        if not check_db_connection():
            logger.error("Could not reach MongoDB server.")
            return False

        db = get_database()

        # 1. Stocks collection indexes
        logger.info("Setting up indexes on 'stocks' collection...")
        db.stocks.create_index([("symbol", ASCENDING)], unique=True, name="uq_stock_symbol")
        db.stocks.create_index([("active", ASCENDING)], name="idx_stock_active")

        # 2. Prices collection indexes
        logger.info("Setting up indexes on 'prices' collection...")
        db.prices.create_index(
            [("symbol", ASCENDING), ("trade_date", ASCENDING)],
            unique=True,
            name="uq_symbol_trade_date",
        )
        db.prices.create_index([("trade_date", ASCENDING)], name="idx_prices_trade_date")
        db.prices.create_index([("symbol", ASCENDING)], name="idx_prices_symbol")

        # 3. RSI collection indexes
        logger.info("Setting up indexes on 'rsi' collection...")
        db.rsi.create_index(
            [("symbol", ASCENDING), ("trade_date", ASCENDING)],
            unique=True,
            name="uq_rsi_symbol_trade_date",
        )
        db.rsi.create_index([("trade_date", ASCENDING)], name="idx_rsi_trade_date")
        db.rsi.create_index([("symbol", ASCENDING)], name="idx_rsi_symbol")
        db.rsi.create_index([("average_rsi", DESCENDING)], name="idx_rsi_average_rsi")

        logger.info(f"MongoDB database '{config.MONGO_DB_NAME}' initialized successfully with all indexes.")
        return True

    except Exception as e:
        logger.error(f"Error during MongoDB initialization: {e}")
        return False


if __name__ == "__main__":
    success = init_database()
    if success:
        print("MongoDB initialization completed successfully.")
    else:
        print("MongoDB initialization failed.")
