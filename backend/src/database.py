import os
from contextlib import contextmanager

from celery import Celery
from loguru import logger
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from .config import get_backend_settings, get_database_settings

# Check if running in test mode
TESTING = os.getenv("TESTING", "false").lower() == "true"

if TESTING:
    # Use SQLite for testing
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///:memory:")
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    logger.info("Using test database configuration")
else:

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


def get_celery_app(name):
    settings = get_backend_settings()
    broker_url = settings.celery_broker_url
    result_backend = settings.celery_result_backend
    if not broker_url or not result_backend:
        raise ValueError(
            "CELERY_BROKER_URL and CELERY_RESULT_BACKEND must be set in environment variables."
        )

    app = Celery(
        name,
        broker=broker_url,
        backend=result_backend,
    )
    app.conf.update(
        task_track_started=True,
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="Asia/Ho_Chi_Minh",
        enable_utc=True,
        worker_max_tasks_per_child=1,
        worker_concurrency=2,
        task_acks_late=True,
        worker_hijack_root_logger=False,
        worker_log_format="[%(asctime)s: %(levelname)s/%(processName)s] %(message)s",
        worker_task_log_format="[%(asctime)s: %(levelname)s/%(processName)s] [%(task_name)s(%(task_id)s)] %(message)s",
    )
    return app
