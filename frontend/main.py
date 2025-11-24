import os
import uuid
import wave
import io
from pathlib import Path
from typing import Optional

import numpy as np
import audioop
import chainlit as cl
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
from chainlit.types import ThreadDict
from helpers import (
    DATABASE_URL,
    call_rag_api,
    call_stt_api,
    call_tts_api,
    simulate_streaming,
)
from loguru import logger


# Audio detection constants
SILENCE_THRESHOLD = 3500  # Adjust based on audio level
SILENCE_TIMEOUT = 1300.0  # Milliseconds of silence to end turn
MAX_AUDIO_DURATION_MS = 30000  # Maximum 30 seconds recording


@cl.data_layer
def get_data_layer():
    return SQLAlchemyDataLayer(conninfo=DATABASE_URL)


@cl.oauth_callback
def oauth_callback(
    provider_id: str,
    token: str,
    raw_user_data: dict,
    default_user: cl.User,
) -> Optional[cl.User]:

    logger.info(f"OAuth callback: provider={provider_id}, user_data={raw_user_data}")

    # Extract user information based on provider
    if provider_id == "google":
        user_id = raw_user_data.get("id")
        email = raw_user_data.get("email")
        name = raw_user_data.get("name", email)
        picture = raw_user_data.get("picture")
    elif provider_id == "github":
        user_id = raw_user_data.get("id")
        email = raw_user_data.get("email")
        name = raw_user_data.get("name") or raw_user_data.get("login", email)
        picture = raw_user_data.get("avatar_url")
    else:
        logger.warning(f"Unknown OAuth provider: {provider_id}")
        return default_user

    identifier = f"{provider_id}:{user_id}"

    return cl.User(
        identifier=identifier,
        metadata={
            "provider": provider_id,
            "email": email,
            "name": name,
            "picture": picture,
            "raw_user_data": raw_user_data,
        },
    )


@cl.on_chat_start
async def on_chat_start():
    user = cl.user_session.get("user")

    if not user:
        logger.error("User not authenticated in on_chat_start")
        await cl.Message(
            content="❌ Authentication required. Please log in to continue."
        ).send()
        return

    # Get user identifier from OAuth callback
    user_identifier = user.identifier
    user_name = user.metadata.get("name", "User")

    logger.info(f"User authenticated: {user_identifier} ({user_name})")

    # Lấy thread_id từ Chainlit context (được tự động tạo bởi Chainlit)
    thread_id = cl.context.session.thread_id

    # Lưu vào session
    cl.user_session.set("thread_id", thread_id)
    cl.user_session.set("user_identifier", user_identifier)

    # Initialize audio session variables
    cl.user_session.set("audio_chunks", [])
    cl.user_session.set("silent_duration_ms", 0)
    cl.user_session.set("is_speaking", False)
    cl.user_session.set("last_elapsed_time", 0)

    logger.info(f"Chat started: user={user_identifier}, thread={thread_id}")

    await cl.Message(
        content=(
            f"👋 **Xin chào {user_name}!**\n\n"
            "Tôi là Meddy - trợ lý y tế AI của bạn.\n\n"
            "💬 **Text mode**: Nhập câu hỏi trực tiếp\n"
            "🎤 **Voice mode**: Nhấn `P` để bắt đầu nói\n\n"
            "_Lưu ý: Voice mode sẽ tự động tắt sau 1.3s im lặng_"
        )
    ).send()


@cl.on_message
async def on_message(message: cl.Message):
    user = cl.user_session.get("user")
    if not user:
        await cl.Message(
            content="❌ **Vui lòng đăng nhập để sử dụng dịch vụ.**\n\nBạn cần đăng nhập bằng GitHub hoặc Google để có thể trò chuyện với Meddy.",
            author="system",
        ).send()
        return

    # Get user identifier
    user_identifier = user.identifier
    user_message = message.content

    # Lấy thread_id từ Chainlit context
    thread_id = cl.context.session.thread_id

    if not thread_id:
        logger.error("No thread_id found in Chainlit context")
        await cl.Message(
            content="❌ **Lỗi hệ thống.**\n\nKhông tìm thấy thread ID. Vui lòng làm mới trang.",
            author="system",
        ).send()
        return

    logger.info(f"Processing message: user={user_identifier}, thread={thread_id}")

    # Create response message with typing indicator
    response_message = cl.Message(content="", author="Meddy")
    await response_message.send()

    try:
        # Show typing indicator
        await response_message.stream_token("🤔 Đang suy nghĩ...\n")

        # Call backend RAG API
        result = await call_rag_api(user_identifier, thread_id, user_message)

        # Clear typing indicator
        response_message.content = ""

        # Stream the response
        response_text = result.get("response", "")
        for chunk in simulate_streaming(response_text):
            await response_message.stream_token(chunk)

        # Add sources if available
        sources = result.get("sources")
        if sources:
            await response_message.stream_token("\n\n---\n\n**📚 Nguồn tham khảo:**\n")
            for i, source in enumerate(sources, 1):
                source_text = (
                    f"{i}. {source.get('title', 'Nguồn')}: {source.get('url', 'N/A')}\n"
                )
                await response_message.stream_token(source_text)

        # Add metadata footer (optional, for debugging)
        metadata = result.get("metadata", {})
        duration = metadata.get("duration_seconds")
        if duration:
            footer = f"\n\n_Thời gian xử lý: {duration:.2f}s_"
            await response_message.stream_token(footer)

    except Exception as e:
        logger.error(f"Error processing message: {e}")
        error_message = (
            "\n\n❌ **Đã có lỗi xảy ra khi xử lý câu hỏi của bạn.**\n\n"
            + f"Chi tiết: {str(e)}\n\n"
        )
        response_message.content = ""
        await response_message.stream_token(error_message)

    await response_message.update()


@cl.on_chat_end
async def on_chat_end():
    user_identifier = cl.user_session.get("user_identifier")
    thread_id = cl.context.session.thread_id
    logger.info(f"Chat ended: user={user_identifier}, thread={thread_id}")


@cl.on_chat_resume
async def on_chat_resume(thread: ThreadDict):
    user = cl.user_session.get("user")
    if not user:
        return

    user_identifier = user.identifier
    thread_id = thread.get("id")

    cl.user_session.set("thread_id", thread_id)
    cl.user_session.set("user_identifier", user_identifier)

    # Re-initialize audio session variables
    cl.user_session.set("audio_chunks", [])
    cl.user_session.set("silent_duration_ms", 0)
    cl.user_session.set("is_speaking", False)
    cl.user_session.set("last_elapsed_time", 0)

    logger.info(f"Chat resumed: user={user_identifier}, thread={thread_id}")


@cl.on_audio_start
async def on_audio_start():
    """Initialize audio recording session"""
    user = cl.user_session.get("user")
    if not user:
        return False

    # Reset audio session state
    cl.user_session.set("audio_chunks", [])
    cl.user_session.set("silent_duration_ms", 0)
    cl.user_session.set("is_speaking", False)
    cl.user_session.set("last_elapsed_time", 0)

    logger.info(f"Audio recording started for user {user.identifier}")
    return True


@cl.on_audio_chunk
async def on_audio_chunk(chunk: cl.InputAudioChunk):
    """
    Process incoming audio chunks and detect silence to auto-stop recording
    """
    audio_chunks = cl.user_session.get("audio_chunks")

    if audio_chunks is None:
        audio_chunks = []
        cl.user_session.set("audio_chunks", audio_chunks)

    # Convert bytes to numpy array and store
    audio_array = np.frombuffer(chunk.data, dtype=np.int16)
    audio_chunks.append(audio_array)

    # If this is the first chunk, initialize timers
    if chunk.isStart:
        cl.user_session.set("last_elapsed_time", chunk.elapsedTime)
        cl.user_session.set("is_speaking", True)
        logger.debug(f"First audio chunk received at {chunk.elapsedTime}ms")
        return

    # Get session state
    last_elapsed_time = cl.user_session.get("last_elapsed_time", 0)
    silent_duration_ms = cl.user_session.get("silent_duration_ms", 0)
    is_speaking = cl.user_session.get("is_speaking", False)

    # Calculate time difference
    time_diff_ms = chunk.elapsedTime - last_elapsed_time
    cl.user_session.set("last_elapsed_time", chunk.elapsedTime)

    # Compute audio energy (RMS)
    audio_energy = audioop.rms(chunk.data, 2)  # 16-bit audio

    # Check if audio exceeds max duration
    if chunk.elapsedTime >= MAX_AUDIO_DURATION_MS:
        logger.info(f"Max audio duration reached: {chunk.elapsedTime}ms")
        cl.user_session.set("is_speaking", False)
        await process_audio()
        return

    if audio_energy < SILENCE_THRESHOLD:
        # Audio is silent
        silent_duration_ms += time_diff_ms
        cl.user_session.set("silent_duration_ms", silent_duration_ms)

        if silent_duration_ms >= SILENCE_TIMEOUT and is_speaking:
            logger.info(
                f"Silence detected for {silent_duration_ms}ms, processing audio"
            )
            cl.user_session.set("is_speaking", False)
            await process_audio()
    else:
        # Audio is active, reset silence timer
        cl.user_session.set("silent_duration_ms", 0)
        if not is_speaking:
            cl.user_session.set("is_speaking", True)


async def process_audio():
    """
    Process accumulated audio chunks: STT → RAG → TTS → Response
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
        # Step 1: Speech-to-Text
        await response_message.stream_token("🎤 **Đang nhận diện giọng nói...**\n\n")

        # Save WAV to temp file for STT API
        audio_dir = Path("/tmp/audio")
        audio_dir.mkdir(parents=True, exist_ok=True)
        temp_audio_path = audio_dir / f"input_{uuid.uuid4().hex}.wav"

        with open(temp_audio_path, "wb") as f:
            f.write(wav_buffer.getvalue())

        # Call STT API
        stt_result = await call_stt_api(str(temp_audio_path))
        transcript = stt_result.get("text", "").strip()

        # Cleanup temp file
        temp_audio_path.unlink(missing_ok=True)

        if not transcript:
            await response_message.stream_token(
                "❌ **Không nhận diện được giọng nói.**\n\n"
                "Vui lòng thử lại với âm thanh rõ ràng hơn."
            )
            await response_message.update()
            return

        # Display transcript
        response_message.content = f"📝 **Bạn:** {transcript}\n\n"
        await response_message.update()

        # Step 2: RAG Query (with length limit for voice mode)
        await response_message.stream_token("🤔 **Đang suy nghĩ...**\n\n")

        # Add instruction to limit response length for voice mode
        voice_query = (
            f"{transcript}\n\n"
            "[VOICE MODE: Please provide a concise answer in Vietnamese, "
            "maximum 300 characters (~85 tokens, 3-4 sentences). "
            "Focus on the most important information.]"
        )

        rag_result = await call_rag_api(user_identifier, thread_id, voice_query)
        response_text = rag_result.get("response", "")

        # Truncate if too long (safety check)
        if len(response_text) > 350:
            response_text = response_text[:300] + "..."
            logger.warning(
                f"Response truncated from {len(rag_result.get('response', ''))} to 300 chars"
            )

        # Clear previous content and display answer
        response_message.content = f"📝 **Bạn:** {transcript}\n\n💬 **Trả lời:**\n\n"

        # Stream the response text
        for chunk in simulate_streaming(response_text):
            await response_message.stream_token(chunk)

        await response_message.update()

        # Step 3: Text-to-Speech
        await response_message.stream_token("\n\n🔊 **Đang tạo giọng nói...**")

        try:
            audio_data = await call_tts_api(response_text)

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

        except Exception as tts_error:
            logger.error(f"TTS error: {tts_error}")
            await response_message.stream_token(
                "\n\n⚠️ _Không thể tạo giọng nói. Bạn vẫn có thể đọc câu trả lời bên trên._"
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

        logger.info(
            f"Audio RAG completed: transcript_len={len(transcript)}, "
            f"response_len={len(response_text)}, duration={duration:.2f}s"
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


@cl.on_audio_end
async def on_audio_end():
    """
    Called when audio recording ends.
    If user manually stops, process any remaining audio.
    """
    is_speaking = cl.user_session.get("is_speaking", False)
    audio_chunks = cl.user_session.get("audio_chunks", [])

    # Only process if user manually stopped and we have audio
    if is_speaking and audio_chunks:
        logger.info("User manually stopped audio recording, processing...")
        await process_audio()
    else:
        logger.debug("Audio recording ended (already processed or no audio)")
