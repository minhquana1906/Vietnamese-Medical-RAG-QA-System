import os
import uuid
from typing import Optional

import chainlit as cl
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
from chainlit.types import ThreadDict
from helpers import DATABASE_URL, call_rag_api, simulate_streaming
from loguru import logger


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

    logger.info(f"Chat started: user={user_identifier}, thread={thread_id}")


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
    """
    Được gọi khi user resume một cuộc trò chuyện cũ
    Chainlit tự động load lại thread và history
    """
    user = cl.user_session.get("user")
    if not user:
        return

    user_identifier = user.identifier
    thread_id = thread.get("id")

    cl.user_session.set("thread_id", thread_id)
    cl.user_session.set("user_identifier", user_identifier)

    logger.info(f"Chat resumed: user={user_identifier}, thread={thread_id}")
