import os
from contextlib import contextmanager

from celery import Celery
from loguru import logger
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

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
    # Production PostgreSQL setup
    POSTGRES_USER = os.getenv("POSTGRES_USER", "posgres_admin")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres_admin")
    POSTGRES_DB = os.getenv("POSTGRES_DB", "demo_bot")
    POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres_db")
    POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
    DATABASE_URL = os.getenv("DATABASE_URL") or (
        f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    )
    try:
        engine = create_engine(DATABASE_URL, pool_pre_ping=True)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
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
    broker_url = os.getenv("CELERY_BROKER_URL")
    result_backend = os.getenv("CELERY_RESULT_BACKEND")
    if not broker_url or not result_backend:
        raise ValueError("CELERY_BROKER_URL and CELERY_RESULT_BACKEND must be set in environment variables.")

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
        worker_max_tasks_per_child=1,  # Restart worker after each task to prevent memory leaks
        worker_concurrency=2,  # Adjust based on your server's CPU cores
        task_acks_late=True,  # Acknowledge tasks after they have been executed
        worker_hijack_root_logger=False,  # Prevent Celery from hijacking the root logger
        worker_log_format="[%(asctime)s: %(levelname)s/%(processName)s] %(message)s",
        worker_task_log_format="[%(asctime)s: %(levelname)s/%(processName)s] [%(task_name)s(%(task_id)s)] %(message)s",
    )
    return app
