import hashlib
import secrets

from loguru import logger


def generate_hash(length=16):
    return secrets.token_hex(length // 2)


def generate_request_id(max_length=32):
    hash_string = generate_hash(length=max_length)
    h = hashlib.sha256()
    h.update(hash_string.encode("utf-8"))
    return h.hexdigest()[: max_length + 1]


def setup_logger():
    logger.add("logs/app.log", rotation="10 MB", retention="30 days", level="INFO")
    logger.info("Logger is set up.")
