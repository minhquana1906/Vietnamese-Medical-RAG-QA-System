import os
import uuid
import chainlit as cl
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
from chainlit.types import ThreadDict
from loguru import logger
from dotenv import load_dotenv

from helpers import call_rag_api, simulate_streaming

load_dotenv()


# DATABASE_URL = os.getenv("DATABASE_URL")
DATABASE_URL = (
    "postgresql+asyncpg://postgresadmin:postgresadmin@postgres_db:5432/medical_rag_db"
)


@cl.oauth_callback
def oauth_callback(provider_id, token, raw_user_data, default_user):
    if provider_id == "google":
        user_id = raw_user_data.get("sub") or raw_user_data.get("id")
        name = raw_user_data.get("name")
        email = raw_user_data.get("email")
        avatar = raw_user_data.get("picture")

        return cl.User(
            identifier=f"google_{user_id}",
            metadata={
                "name": name,
                "email": email,
                "picture": avatar,
                "provider": provider_id,
                "role": "user",
            },
        )

    elif provider_id == "github":
        email = raw_user_data.get("email")
        if not email:
            import requests

            headers = {"Authorization": f"token {token}"}
            emails = requests.get(
                "https://api.github.com/user/emails", headers=headers
            ).json()
            primary = next((e["email"] for e in emails if e.get("primary")), None)
            email = primary or emails[0]["email"]

        user_id = str(raw_user_data.get("id"))
        name = raw_user_data.get("name") or raw_user_data.get("login")
        avatar = raw_user_data.get("avatar_url")

        return cl.User(
            identifier=user_id,
            metadata={
                "name": name,
                "email": email,
                "picture": avatar,
                "provider": provider_id,
                "role": "user",
            },
        )

    return default_user


@cl.on_chat_start
async def start():
    user = cl.user_session.get("user")

    if user:
        user_metadata = user.metadata or {}
        user_name = user_metadata.get("name", "bạn")
        greeting = f"**Xin chào {user_name}!** 👋\n\n"
    else:
        greeting = "**Xin chào!** 👋\n\n"

    welcome_message = (
        greeting
        + "Tôi là **Meddy** 🤓 - trợ lý y khoa thông minh của bạn.\n\n"
        + "Tôi có thể giúp bạn:\n"
        + "- 💊 Tư vấn về các bệnh lý và triệu chứng\n"
        + "- 🏥 Hướng dẫn chăm sóc sức khỏe\n"
        + "- 💉 Giải đáp thông tin về thuốc và điều trị\n"
        + "- 🔬 Cung cấp kiến thức y khoa dựa trên nguồn đáng tin cậy\n\n"
        + "Hãy đặt câu hỏi của bạn và tôi sẽ cố gắng giúp bạn! 😊"
    )

    await cl.Message(content=welcome_message, author="Meddy").send()


@cl.on_message
async def main(message: cl.Message):
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

    # Get or create thread ID
    thread_id = cl.user_session.get("thread_id")
    if not thread_id:
        thread_id = str(uuid.uuid4())
        cl.user_session.set("thread_id", thread_id)
        logger.info(f"Created new thread: {thread_id} for user: {user_identifier}")

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
            + "Vui lòng thử lại sau hoặc liên hệ quản trị viên nếu lỗi vẫn tiếp diễn."
        )
        response_message.content = ""
        await response_message.stream_token(error_message)

    await response_message.update()


@cl.data_layer
def get_data_layer():
    return SQLAlchemyDataLayer(conninfo=DATABASE_URL)


@cl.on_chat_resume
async def on_chat_resume(thread: ThreadDict):
    """Resume an existing conversation thread"""
    thread_id = thread.get("id")
    thread_name = thread.get("name", "Cuộc trò chuyện")

    logger.info(f"Resuming thread: {thread_id}")

    # Store thread ID in session
    cl.user_session.set("thread_id", thread_id)


@cl.on_settings_update
async def on_settings_update(settings):
    logger.info(f"Settings updated: {settings}")
    cl.user_session.set("settings", settings)
