import os
import time
import uuid
import wave
import io
from pathlib import Path
import numpy as np

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

            # Debug logging
            logger.debug(f"RAG API raw response: {result}")

            # Validate response structure
            if result is None:
                logger.error("RAG API returned None (null JSON)")
                raise Exception("Backend returned null response")

            if not isinstance(result, dict):
                logger.error(f"RAG API returned non-dict: {type(result)}")
                raise Exception(f"Invalid response type: {type(result)}")

            # Check for required fields
            if "response" not in result:
                logger.error(f"RAG API missing 'response' field. Keys: {result.keys()}")
                raise Exception("Invalid response format: missing 'response' field")

            logger.info(
                f"RAG API success: response_len={len(result.get('response', ''))}, has_sources={bool(result.get('sources'))}"
            )
            return result

        except httpx.TimeoutException as e:
            logger.error(f"RAG API timeout: {e}")
            raise
        except httpx.ConnectError as e:
            logger.error(f"RAG API connection error: {e}")
            raise
        except httpx.HTTPStatusError as e:
            logger.error(f"RAG API HTTP error: {e.response.status_code}")
            error_detail = e.response.text if e.response else str(e)
            logger.error(f"Response body: {error_detail[:500]}")
            raise Exception(f"Backend API error: {e.response.status_code}")
        except Exception as e:
            logger.error(f"RAG API unexpected error: {e}", exc_info=True)
            raise  # Always re-raise to prevent None return


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


async def process_audio():
    """
    Process accumulated audio chunks: Speech-to-Speech RAG Pipeline

    Uses /v1/rag/audio endpoint for full pipeline (STT → RAG → TTS)
    This endpoint handles thread creation and uses speech-optimized prompt
    """
    user = cl.user_session.get("user")
    if not user:
        return

    user_identifier = user.identifier
    thread_id = cl.context.session.thread_id

    # Get accumulated audio chunks
    audio_chunks = cl.user_session.get("audio_chunks", [])

    if not audio_chunks:
        logger.warning("No audio chunks to process")
        return

    # Reset audio chunks for next recording
    cl.user_session.set("audio_chunks", [])

    # Concatenate all chunks into single audio array
    concatenated_audio = np.concatenate(audio_chunks)

    # Create WAV file in memory
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, "wb") as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(24000)  # 24kHz PCM (Chainlit default)
        wav_file.writeframes(concatenated_audio.tobytes())

    wav_buffer.seek(0)

    # Check audio duration
    frames = concatenated_audio.shape[0]
    duration = frames / 24000.0  # Sample rate

    if duration <= 0.5:
        logger.warning(f"Audio too short: {duration:.2f}s")
        await cl.Message(
            content="⚠️ **Audio quá ngắn.** Vui lòng nói lâu hơn (tối thiểu 0.5s).",
            author="system",
        ).send()
        return

    logger.info(f"Processing audio: duration={duration:.2f}s, user={user_identifier}")

    # Create response message
    response_message = cl.Message(content="", author="Meddy")
    await response_message.send()

    try:
        # Save WAV to temp file for Audio RAG API
        await response_message.stream_token("🎤 **Đang xử lý giọng nói...**\n\n")

        audio_dir = Path("/tmp/audio")
        audio_dir.mkdir(parents=True, exist_ok=True)
        temp_audio_path = audio_dir / f"input_{uuid.uuid4().hex}.wav"

        with open(temp_audio_path, "wb") as f:
            f.write(wav_buffer.getvalue())

        # Call Audio RAG API (STT → RAG → TTS in one call)
        rag_result = await call_audio_rag_api(
            user_identifier, thread_id, str(temp_audio_path)
        )

        # Cleanup temp file
        temp_audio_path.unlink(missing_ok=True)

        # Extract results
        transcript = rag_result.get("transcript", "").strip()
        response_text = rag_result.get("response", "")
        audio_url = rag_result.get("audio_url", "")

        # DEBUG: Log audio_url
        logger.info(f"Received audio_url from backend: '{audio_url}'")

        if not transcript:
            await response_message.stream_token(
                "❌ **Không nhận diện được giọng nói.**\n\n"
                "Vui lòng thử lại với âm thanh rõ ràng hơn."
            )
            await response_message.update()
            return

        # Display transcript
        response_message.content = f"📝 **Bạn:** {transcript}\n\n💬 **Trả lời:**\n\n"
        await response_message.update()

        # Stream the response text
        for chunk in simulate_streaming(response_text):
            await response_message.stream_token(chunk)

        await response_message.update()

        # Fetch and attach audio response
        if audio_url:
            try:
                await response_message.stream_token("\n\n🔊 **Đang tải audio...**")

                # Download audio from backend
                audio_fetch_url = f"{BACKEND_API_URL}{audio_url}"
                async with httpx.AsyncClient(timeout=30.0) as client:
                    audio_response = await client.get(audio_fetch_url)
                    audio_response.raise_for_status()
                    audio_data = audio_response.content

                # Create Audio element for playback
                output_audio_el = cl.Audio(
                    name="response_audio",
                    content=audio_data,
                    mime="audio/mpeg",
                    auto_play=True,
                    display="inline",
                )

                response_message.elements = [output_audio_el]

                # Update final message
                response_message.content = (
                    f"📝 **Bạn:** {transcript}\n\n"
                    f"💬 **Trả lời:**\n\n{response_text}\n\n"
                    f"🔊 _Đang phát audio..._"
                )
                await response_message.update()

            except Exception as audio_error:
                logger.error(f"Audio download error: {audio_error}")
                await response_message.stream_token(
                    "\n\n⚠️ _Không thể tải audio. Bạn vẫn có thể đọc câu trả lời bên trên._"
                )
                await response_message.update()

        # Add sources (optional, compact format for voice mode)
        sources = rag_result.get("sources", [])
        if sources and len(sources) > 0:
            await response_message.stream_token("\n\n---\n📚 _Nguồn: ")
            source_titles = [
                s.get("title", "N/A") for s in sources[:2]
            ]  # Max 2 sources
            await response_message.stream_token(", ".join(source_titles) + "_")
            await response_message.update()

        # Log metadata
        metadata = rag_result.get("metadata", {})
        logger.info(
            f"Audio RAG completed: "
            f"transcript_len={len(transcript)}, "
            f"response_len={len(response_text)}, "
            f"stt={metadata.get('stt_duration', 0):.2f}s, "
            f"rag={metadata.get('rag_duration', 0):.2f}s, "
            f"tts={metadata.get('tts_duration', 0):.2f}s, "
            f"total={metadata.get('total_duration', 0):.2f}s"
        )

    except Exception as e:
        logger.error(f"Error processing audio: {e}", exc_info=True)
        error_message = (
            f"📝 **Bạn:** {transcript if 'transcript' in locals() else 'N/A'}\n\n"
            f"❌ **Lỗi:** {str(e)}\n\n"
            "Vui lòng thử lại."
        )
        response_message.content = error_message
        await response_message.update()
