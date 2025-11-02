import hashlib
import secrets

from loguru import logger

from .core.cache import get_redis_client
from .database import get_db_session
from .schemas.schema import HealthCheckResponse


def generate_hash(length=16):
    return secrets.token_hex(length // 2)


async def check_database_health() -> HealthCheckResponse:
    try:
        db = next(get_db_session())
        db.execute("SELECT 1")
        db.close()
        return HealthCheckResponse(
            status="ok",
            service="database",
            details={"type": "postgresql", "message": "Connected"},
        )
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return HealthCheckResponse(
            status="error", service="database", details={"error": str(e)}
        )


async def check_cache_health() -> HealthCheckResponse:
    try:
        redis_client = get_redis_client()
        redis_client.ping()

        info = redis_client.info("stats")
        return HealthCheckResponse(
            status="ok",
            service="cache",
            details={
                "type": "redis",
                "message": "Connected",
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
            },
        )
    except Exception as e:
        logger.error(f"Cache health check failed: {e}")
        return HealthCheckResponse(
            status="error", service="cache", details={"error": str(e)}
        )
