import os
from contextlib import contextmanager

from celery import Celery
from loguru import logger
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from .configs.setup import get_backend_settings, get_database_settings

settings = get_database_settings()

try:
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    logger.info("Database connection established successfully.")
except OperationalError as e:
    logger.error(f"Database connection error: {e}")
    raise


@contextmanager
def get_db():
    db = SessionLocal()
    try:
        yield db
    except OperationalError as e:
        db.rollback()
        logger.error(f"Database connection error: {e}")
        raise
    finally:
        db.close()
