from sqlalchemy import text
from app.config import config
from app.database.connection import get_engine
from app.database.models import Base
from app.utils.logger import logger

def init_database() -> bool:
    """
    Initializes the MySQL database and creates all tables, indexes, and constraints.
    Safe to run multiple times.
    """
    try:
        logger.info(f"Checking/Creating MySQL Database '{config.DB_NAME}'...")
        
        # 1. Connect to MySQL server without specifying a target database
        root_engine = get_engine(with_db=False)
        with root_engine.connect() as conn:
            # Issue CREATE DATABASE IF NOT EXISTS statement
            create_db_sql = text(
                f"CREATE DATABASE IF NOT EXISTS `{config.DB_NAME}` "
                f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
            )
            conn.execute(create_db_sql)
            conn.commit()
            logger.info(f"Database '{config.DB_NAME}' ensured.")
        
        root_engine.dispose()

        # 2. Connect to the target database and create all tables via SQLAlchemy metadata
        db_engine = get_engine(with_db=True)
        logger.info("Creating tables, foreign keys, and indexes if they do not exist...")
        Base.metadata.create_all(bind=db_engine)
        
        logger.info("All database tables initialized successfully.")
        return True

    except Exception as e:
        logger.error(f"Error during database initialization: {e}")
        return False

if __name__ == "__main__":
    success = init_database()
    if success:
        print("Database initialization completed successfully.")
    else:
        print("Database initialization failed.")
