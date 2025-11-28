import hashlib
import json
import uuid
from typing import Any, Dict, List, Optional

import redis
from loguru import logger

from ..configs.setup import get_backend_settings

settings = get_backend_settings()


# Cache metrics
def _get_cache_metrics():
    """Get cache metrics from centralized metrics module"""
    try:
        from .metrics import cache_hits_total, cache_misses_total

        return cache_hits_total, cache_misses_total
    except ImportError:
        return None, None


def generate_request_id(max_length=32):
    hash_string = str(uuid.uuid4())
    h = hashlib.sha256()
    h.update(hash_string.encode("utf-8"))
    return h.hexdigest()[:max_length]


def get_redis_client(host=None, port=None, db=None, password=None):
    try:
        host = settings.redis_host
        port = settings.redis_port
        db = settings.redis_db
        password = settings.redis_password

        if password:
            client = redis.Redis(host=host, port=port, db=db, password=password)
        else:
            client = redis.Redis(host=host, port=port, db=db)

        client.ping()
        return client
    except Exception as e:
        logger.error(f"[CACHE] Redis connection failed: {e}")
        raise


def get_conversation_id(bot_id, user_id, ttl_seconds=360):
    key = f"{bot_id}.{user_id}"
    try:
        client = get_redis_client()

        if client.exists(key):
            client.expire(key, ttl_seconds)
            return client.get(key).decode("utf-8")
        else:
            conversation_id = generate_request_id()
            client.set(key, conversation_id, ex=ttl_seconds)
            return conversation_id
    except Exception as e:
        logger.error(f"[CACHE] Conversation ID error: {e}")
        raise


def delete_conversation_id(bot_id, user_id):
    key = f"{bot_id}.{user_id}"
    try:
        client = get_redis_client()
        if client.exists(key):
            client.delete(key)
            return True
        else:
            return False
    except Exception as e:
        logger.error(f"[CACHE] Delete conversation error: {e}")
        raise


def _generate_cache_key(prefix: str, content: str) -> str:
    content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()
    return f"{prefix}:{content_hash}"


def get_query_embedding(query: str) -> Optional[List[float]]:
    key = _generate_cache_key("emb", query)
    try:
        client = get_redis_client()
        cached = client.get(key)
        cache_hits_total, cache_misses_total = _get_cache_metrics()

        if cached:
            if cache_hits_total:
                cache_hits_total.labels(cache_type="embedding").inc()
            result: List[float] = json.loads(cached)
            return result

        if cache_misses_total:
            cache_misses_total.labels(cache_type="embedding").inc()
        return None
    except Exception as e:
        logger.warning(f"[CACHE] Embedding retrieval error: {e}")
        return None


def cache_query_embedding(
    query: str, embedding: List[float], ttl_seconds: int = 3600
) -> bool:
    key = _generate_cache_key("emb", query)
    try:
        client = get_redis_client()
        client.setex(key, ttl_seconds, json.dumps(embedding))
        return True
    except Exception as e:
        logger.warning(f"[CACHE] Embedding cache error: {e}")
        return False


def get_search_results(
    query: str, search_type: str = "hybrid"
) -> Optional[List[Dict[str, Any]]]:
    key = _generate_cache_key(f"search:{search_type}", query)
    try:
        client = get_redis_client()
        cached = client.get(key)
        cache_hits_total, cache_misses_total = _get_cache_metrics()

        if cached:
            if cache_hits_total:
                cache_hits_total.labels(cache_type="search").inc()
            result: List[Dict[str, Any]] = json.loads(cached)
            return result

        if cache_misses_total:
            cache_misses_total.labels(cache_type="search").inc()
        return None
    except Exception as e:
        logger.warning(f"[CACHE] Search results retrieval error: {e}")
        return None


def cache_search_results(
    query: str,
    results: List[Dict[str, Any]],
    search_type: str = "hybrid",
    ttl_seconds: int = 600,
) -> bool:
    key = _generate_cache_key(f"search:{search_type}", query)
    try:
        client = get_redis_client()
        client.setex(key, ttl_seconds, json.dumps(results))
        return True
    except Exception as e:
        logger.warning(f"[CACHE] Search results cache error: {e}")
        return False


def invalidate_search_cache(document_id: Optional[int] = None) -> int:
    try:
        client = get_redis_client()
        pattern = "search:*"
        keys = client.keys(pattern)
        if keys:
            deleted: int = client.delete(*keys)
            return deleted
        return 0
    except Exception as e:
        logger.warning(f"[CACHE] Invalidation error: {e}")
        return 0


def get_cache_stats() -> Dict[str, Any]:
    try:
        client = get_redis_client()
        info = client.info("stats")

        emb_keys = len(client.keys("emb:*"))
        search_keys = len(client.keys("search:*"))
        conv_keys = len(client.keys("*.*"))

        return {
            "total_keys": client.dbsize(),
            "embedding_cache_keys": emb_keys,
            "search_cache_keys": search_keys,
            "conversation_keys": conv_keys,
            "keyspace_hits": info.get("keyspace_hits", 0),
            "keyspace_misses": info.get("keyspace_misses", 0),
            "hit_rate": (
                info.get("keyspace_hits", 0)
                / (info.get("keyspace_hits", 0) + info.get("keyspace_misses", 1))
                if (info.get("keyspace_hits", 0) + info.get("keyspace_misses", 0)) > 0
                else 0.0
            ),
        }
    except Exception as e:
        logger.warning(f"[CACHE] Stats retrieval error: {e}")
        return {"error": str(e)}


# ============= GENERIC CACHE FUNCTIONS =============


def get_cached_value(key: str) -> Optional[str]:
    """Get cached value from Redis by key."""
    try:
        client = get_redis_client()
        cached = client.get(key)
        if cached:
            return cached.decode("utf-8")
        return None
    except Exception as e:
        logger.warning(f"[CACHE] Get value error: {e}")
        return None


def set_cached_value(key: str, value: str, expiration: int = 3600) -> bool:
    """Set cached value in Redis."""
    try:
        client = get_redis_client()
        client.setex(key, expiration, value)
        return True
    except Exception as e:
        logger.warning(f"[CACHE] Set value error: {e}")
        return False
