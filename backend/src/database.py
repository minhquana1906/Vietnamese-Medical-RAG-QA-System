from contextlib import contextmanager

from loguru import logger
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from .configs.setup import get_database_settings

settings = get_database_settings()

try:
    logger.debug(f"Connecting to database at {settings.database_url}")
    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,  # Verify connections before using
        pool_size=10,  # Number of connections to keep open
        max_overflow=20,  # Additional connections allowed when pool is full
        pool_recycle=3600,  # Recycle connections after 1 hour
        echo=False,  # Set to True for SQL query logging
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    logger.info("Database connection established successfully with connection pooling.")
except OperationalError as e:
    logger.error(f"Database connection error: {e}")
    raise


@contextmanager
def get_db():
    """Context manager for database sessions (legacy usage)."""
    db = SessionLocal()
    try:
        yield db
    except OperationalError as e:
        db.rollback()
        logger.error(f"Database connection error: {e}")
        raise
    finally:
        db.close()


def get_db_session():
    """FastAPI dependency for database sessions (new Chainlit endpoints)."""
    db = SessionLocal()
    try:
        yield db
    except OperationalError as e:
        db.rollback()
        logger.error(f"Database error during request: {e}")
        raise
    finally:
        db.close()
