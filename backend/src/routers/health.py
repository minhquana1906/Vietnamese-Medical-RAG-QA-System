"""Health Check and Monitoring Endpoints"""

from fastapi import APIRouter, HTTPException
from loguru import logger

from ..helpers import check_cache_health, check_database_health
from ..schemas.schema import (
    CacheStatisticsResponse,
    HealthCheckResponse,
    SystemHealthResponse,
)

router = APIRouter(prefix="/v1", tags=["Health & Monitoring"])


@router.get("/ready")
async def readiness_check():
    """Readiness probe for Kubernetes/Docker"""
    try:
        await check_database_health()
        return {"status": "ready"}
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        raise HTTPException(status_code=503, detail="Service not ready")


@router.get("/health", response_model=SystemHealthResponse)
async def health_check():
    """Comprehensive health check for all services"""
    from opentelemetry import trace

    tracer = trace.get_tracer(__name__)

    with tracer.start_as_current_span("health_check"):
        database_status = await check_database_health()
        cache_status = await check_cache_health()

        # Determine overall status
        all_healthy = database_status.status == "ok" and cache_status.status == "ok"

        return SystemHealthResponse(
            status="healthy" if all_healthy else "unhealthy",
            api=HealthCheckResponse(
                status="ok", service="api", message="API is running"
            ),
            database=database_status,
            cache=cache_status,
        )


@router.get("/cache/stats", response_model=CacheStatisticsResponse)
async def get_cache_statistics():
    """
    Get comprehensive cache statistics including hit rate, entry counts, and memory usage.

    Returns:
        CacheStatisticsResponse: Cache performance metrics
    """
    from ..core.cache import get_cache_stats

    try:
        stats = get_cache_stats()

        return CacheStatisticsResponse(
            total_keys=stats.get("total_keys", 0),
            embedding_cache_keys=stats.get("embedding_cache_keys", 0),
            search_cache_keys=stats.get("search_cache_keys", 0),
            conversation_keys=stats.get("conversation_keys", 0),
            keyspace_hits=stats.get("keyspace_hits", 0),
            keyspace_misses=stats.get("keyspace_misses", 0),
            hit_rate=stats.get("hit_rate", 0.0),
            memory_used=None,  # Not available from Redis INFO stats
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get cache statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))
