import asyncio
import os
import time

import chainlit as cl
import httpx
from loguru import logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

# Backend API configuration
BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://chatbot_api:8000")
RAG_QUERY_ENDPOINT = f"{BACKEND_API_URL}/v1/rag"
STT_ENDPOINT = f"{BACKEND_API_URL}/v1/models/stt"
TTS_ENDPOINT = f"{BACKEND_API_URL}/v1/models/tts"
AUDIO_RAG_ENDPOINT = f"{BACKEND_API_URL}/v1/rag/audio"
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


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
)
async def call_stt_api(audio_file_path: str) -> dict:
    """
    Transcribe audio file to text using backend STT endpoint

    Args:
        audio_file_path: Path to audio file

    Returns:
        dict with keys: text (transcript), duration (seconds)
    """
    logger.info(f"Calling STT API: audio_file={audio_file_path}")

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            with open(audio_file_path, "rb") as audio_file:
                files = {"file": audio_file}
                response = await client.post(STT_ENDPOINT, files=files)
                response.raise_for_status()
                result = response.json()
                logger.info(
                    f"STT API success: transcript_length={len(result.get('text', ''))}"
                )
                return result
        except httpx.TimeoutException as e:
            logger.error(f"STT API timeout: {e}")
            raise
        except httpx.ConnectError as e:
            logger.error(f"STT API connection error: {e}")
            raise
        except httpx.HTTPStatusError as e:
            logger.error(f"STT API HTTP error: {e}")
            raise Exception(f"Backend STT error: {e.response.status_code}")
        except Exception as e:
            logger.error(f"STT API unexpected error: {e}")
            raise Exception(f"Unexpected error: {str(e)}")


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
)
async def call_tts_api(text: str, voice_id: str = None) -> bytes:
    """
    Synthesize text to speech using backend TTS endpoint

    Args:
        text: Text to synthesize
        voice_id: Optional voice identifier

    Returns:
        bytes: Audio file content
    """
    logger.info(f"Calling TTS API: text_length={len(text)}")

    payload = {"text": text}
    if voice_id:
        payload["voice_id"] = voice_id

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(TTS_ENDPOINT, json=payload)
            response.raise_for_status()
            audio_data = response.content
            logger.info(f"TTS API success: audio_size={len(audio_data)} bytes")
            return audio_data
        except httpx.TimeoutException as e:
            logger.error(f"TTS API timeout: {e}")
            raise
        except httpx.ConnectError as e:
            logger.error(f"TTS API connection error: {e}")
            raise
        except httpx.HTTPStatusError as e:
            logger.error(f"TTS API HTTP error: {e}")
            raise Exception(f"Backend TTS error: {e.response.status_code}")
        except Exception as e:
            logger.error(f"TTS API unexpected error: {e}")
            raise Exception(f"Unexpected error: {str(e)}")


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
)
async def call_audio_rag_api(
    user_identifier: str, thread_id: str, audio_file_path: str
) -> dict:
    """
    Process audio query through full speech-to-speech RAG pipeline

    Args:
        user_identifier: User identifier
        thread_id: Thread/conversation ID
        audio_file_path: Path to audio file with user's question

    Returns:
        dict with keys: response, transcript, sources, metadata, audio_url
    """
    logger.info(
        f"Calling Audio RAG API: user={user_identifier}, thread={thread_id}, audio={audio_file_path}"
    )

    async with httpx.AsyncClient(timeout=180.0) as client:
        try:
            with open(audio_file_path, "rb") as audio_file:
                files = {"file": audio_file}
                data = {
                    "user_identifier": user_identifier,
                    "thread_id": thread_id,
                }
                response = await client.post(AUDIO_RAG_ENDPOINT, files=files, data=data)
                response.raise_for_status()
                result = response.json()
                logger.info(f"Audio RAG API success: {result.get('metadata', {})}")
                return result
        except httpx.TimeoutException as e:
            logger.error(f"Audio RAG API timeout: {e}")
            raise
        except httpx.ConnectError as e:
            logger.error(f"Audio RAG API connection error: {e}")
            raise
        except httpx.HTTPStatusError as e:
            logger.error(f"Audio RAG API HTTP error: {e}")
            raise Exception(f"Backend Audio RAG error: {e.response.status_code}")
        except Exception as e:
            logger.error(f"Audio RAG API unexpected error: {e}")
            raise Exception(f"Unexpected error: {str(e)}")
