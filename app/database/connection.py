from contextlib import contextmanager
from typing import Generator
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session
from app.config import config
from app.utils.logger import logger

# Module-level engine and sessionmaker cache
_engine: Engine | None = None
_SessionFactory: sessionmaker[Session] | None = None

def get_engine(with_db: bool = True) -> Engine:
    """
    Creates or retrieves the SQLAlchemy engine.
    """
    global _engine
    if not with_db:
        # Create a temporary engine without a specific database target
        url = config.get_database_url(with_db=False)
        return create_engine(url, pool_pre_ping=True, echo=False)

    if _engine is None:
        url = config.get_database_url(with_db=True)
        try:
            _engine = create_engine(
                url,
                pool_pre_ping=True,
                pool_recycle=3600,
                pool_size=10,
                max_overflow=20,
                echo=False
            )
            logger.info("SQLAlchemy Database Engine initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize SQLAlchemy Database Engine: {e}")
            raise
    return _engine

def get_session_factory() -> sessionmaker[Session]:
    """
    Returns the session factory instance.
    """
    global _SessionFactory
    if _SessionFactory is None:
        engine = get_engine(with_db=True)
        _SessionFactory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return _SessionFactory

@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Context manager for database sessions.
    Automatically commits on success or rolls back on exception.
    Always closes session upon completion.
    """
    factory = get_session_factory()
    session: Session = factory()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Database session error. Transaction rolled back: {e}")
        raise
    finally:
        session.close()

def check_db_connection() -> bool:
    """
    Tests connectivity to the MySQL server and target database.
    """
    try:
        engine = get_engine(with_db=True)
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1"))
            fetch_val = result.scalar()
            if fetch_val == 1:
                logger.info(f"Database connection test successful on target '{config.DB_NAME}'.")
                return True
    except Exception as e:
        logger.error(f"Database connection check failed: {e}")
        return False
    return False
