"""Health Check and Monitoring Endpoints"""

from fastapi import APIRouter, HTTPException
from loguru import logger

from ..schemas.schema import (
    HealthCheckResponse,
    SystemHealthResponse,
    CacheStatisticsResponse,
)
from ..helpers import check_cache_health, check_database_health

router = APIRouter(prefix="/v1", tags=["Health & Monitoring"])


@router.get("/ready")
async def readiness_check():
    """Readiness probe for Kubernetes/Docker"""
    try:
        check_database_health()
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
        database_status = check_database_health()
        cache_status = check_cache_health()

        return SystemHealthResponse(
            status="healthy" if database_status and cache_status else "unhealthy",
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
            hit_rate=stats.get("hit_rate", 0.0),
            total_hits=stats.get("total_hits", 0),
            total_misses=stats.get("total_misses", 0),
            total_entries=stats.get("total_entries", 0),
            memory_used_bytes=stats.get("memory_used_bytes", 0),
            memory_peak_bytes=stats.get("memory_peak_bytes", 0),
            evictions=stats.get("evictions", 0),
            cache_namespaces=stats.get("cache_namespaces", {}),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get cache statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))
