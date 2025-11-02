import asyncio
import os
import time

import chainlit as cl
import httpx
from loguru import logger
from tenacity import (retry, retry_if_exception_type, stop_after_attempt,
                      wait_exponential)

# Backend API configuration
BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://chatbot_api:8000")
RAG_QUERY_ENDPOINT = f"{BACKEND_API_URL}/v1/rag/query"
DATABASE_URL = (
    "postgresql+asyncpg://postgresadmin:postgresadmin@postgres_db:5432/medical_rag_db"
)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
)
async def call_rag_api(user_identifier: str, thread_id: str, query: str):
    logger.info(f"Calling RAG API: user={user_identifier}, thread={thread_id}")

    payload = {
        "user_identifier": user_identifier,
        "thread_id": thread_id,
        "query": query,
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            response = await client.post(RAG_QUERY_ENDPOINT, json=payload)
            response.raise_for_status()
            result = response.json()
            logger.info(f"RAG API success: {result.get('metadata', {})}")
            return result
        except httpx.TimeoutException as e:
            logger.error(f"RAG API timeout: {e}")
            raise
        except httpx.ConnectError as e:
            logger.error(f"RAG API connection error: {e}")
            raise
        except httpx.HTTPStatusError as e:
            logger.error(f"RAG API HTTP error: {e}")
            raise Exception(f"Backend API error: {e.response.status_code}")
        except Exception as e:
            logger.error(f"RAG API unexpected error: {e}")
            raise Exception(f"Unexpected error: {str(e)}")


def simulate_streaming(text: str, delay: float = 0.0):
    if not text or not isinstance(text, str):
        return

    current_word = ""
    for char in text:
        if char == " ":
            if current_word:
                yield current_word
                current_word = ""
            yield " "
            time.sleep(delay)
        elif char == "\n":
            if current_word:
                yield current_word
                current_word = ""
            yield "\n"
            time.sleep(delay)
        else:
            current_word += char

    # Yield the last word if any
    if current_word:
        yield current_word
