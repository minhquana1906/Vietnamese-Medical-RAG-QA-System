import os

import redis
from loguru import logger

from .utils import generate_request_id

REDIS_HOST = os.getenv("REDIS_HOST", "valkey_db")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))


def get_redis_client(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB):
    try:
        client = redis.Redis(host=host, port=port, db=db)
        client.ping()
        return client
    except Exception as e:
        logger.error(f"Error connecting to Redis: {e}")
        raise


def get_conversation_id(bot_id, user_id, ttl_seconds=360):
    key = f"{bot_id}.{user_id}"
    try:
        client = get_redis_client()

        if client.exists(key):
            client.expire(key, ttl_seconds)  # Refresh TTL
            return client.get(key).decode("utf-8")
        else:
            conversation_id = generate_request_id()
            client.set(key, conversation_id, ex=ttl_seconds)
            logger.info(f"New conversation started: {key} → {conversation_id}")
            return conversation_id
    except Exception as e:
        logger.error(f"Error managing conversation ID in Redis: {e}")
        raise


def delete_conversation_id(bot_id, user_id):
    key = f"{bot_id}.{user_id}"
    try:
        client = get_redis_client()
        if client.exists(key):
            client.delete(key)
            logger.info(f"Deleted conversation ID for {key}")
            return True
        else:
            logger.info(f"No conversation ID found for {key} to delete")
            return False
    except Exception as e:
        logger.error(f"Error deleting conversation ID in Redis: {e}")
        raise
