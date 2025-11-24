from typing import Optional

import numpy as np
import audioop
import chainlit as cl
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
from chainlit.types import ThreadDict
from helpers import DATABASE_URL, call_rag_api, simulate_streaming, process_audio
from loguru import logger


# Audio detection constants
# ============================================================================
# GIẢI THÍCH CÁC THAM SỐ AUDIO:
#
# 1. SILENCE_THRESHOLD (0-32768):
#    - Ngưỡng năng lượng âm thanh để phát hiện im lặng
#    - RMS (Root Mean Square) của audio 16-bit: 0 = hoàn toàn im lặng, 32768 = max volume
#    - Giá trị thấp (500-1500): Nhạy hơn, dễ dàng kết thúc recording
#    - Giá trị cao (3000-5000): Ít nhạy, chờ lâu hơn trước khi kết thúc
#    - Recommended: 2000-3500 cho môi trường ít ồn, 4000-6000 cho môi trường ồn
#
# 2. SILENCE_TIMEOUT (milliseconds):
#    - Thời gian im lặng liên tục để tự động kết thúc recording
#    - Giá trị thấp (500-1000ms): Kết thúc nhanh, phù hợp câu ngắn
#    - Giá trị cao (2000-3000ms): Chờ lâu hơn, phù hợp câu dài/suy nghĩ giữa chừng
#    - Recommended: 1500-2000ms cho input dài
#
# 3. MAX_AUDIO_DURATION_MS (milliseconds):
#    - Giới hạn thời gian recording tối đa (tránh recording vô hạn)
#    - Recommended: 60000ms (60s) cho input dài, 30000ms (30s) cho input ngắn
#
# 4. sample_rate (trong config.toml):
#    - Tần số lấy mẫu audio (Hz)
#    - 16000 Hz: Chất lượng đủ cho STT, tiết kiệm băng thông
#    - 24000 Hz: Chất lượng tốt hơn, cân bằng giữa quality và size
#    - 44100 Hz: Chất lượng cao (music), không cần thiết cho speech
#    - Recommended: 16000-24000 Hz cho voice input
# ============================================================================

SILENCE_THRESHOLD = 1500  # Giảm từ 3500 để nhạy hơn với im lặng
SILENCE_TIMEOUT = 1500.0  # Tăng từ 1300ms lên 2000ms cho input dài hơn
MAX_AUDIO_DURATION_MS = 30000  # Tăng từ 30s lên 60s để cho phép câu hỏi dài


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
            f"_Lưu ý: Voice mode sẽ tự động tắt sau {SILENCE_TIMEOUT / 1000:.1f}s im lặng_"
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

        # Debug: Log what we actually got
        logger.debug(f"call_rag_api returned: type={type(result)}, value={result}")

        # Safety check: ensure result is not None
        if result is None:
            logger.error("RAG API returned None")
            raise Exception("Đã có lỗi xảy ra khi kết nối với backend")

        # Clear typing indicator
        response_message.content = ""

        # Stream the response
        response_text = result.get("response", "")

        # Validate response text
        if not response_text:
            logger.warning("Empty response text from backend")
            response_text = "Xin lỗi, tôi không thể tạo câu trả lời cho câu hỏi này."

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
        metadata = result.get("metadata") or {}  # Handle None from backend
        if metadata:
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
