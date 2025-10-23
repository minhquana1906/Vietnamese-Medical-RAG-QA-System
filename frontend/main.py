
import os

from dotenv import load_dotenv

load_dotenv()

print("GITHUB_CLIENT_ID:", os.getenv("GITHUB_CLIENT_ID"))
print("GITHUB_CLIENT_SECRET:", os.getenv("GITHUB_CLIENT_SECRET"))
print("CHAINLIT_AUTH_SECRET:", os.getenv("CHAINLIT_AUTH_SECRET"))

from typing import Dict, Optional

import chainlit as cl
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
from chainlit.types import ThreadDict
from helper import streaming_response_generator

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres_admin")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres_password")
    POSTGRES_DB = os.getenv("POSTGRES_DB", "chat_conversation_db")
    POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres_db")
    POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
    DATABASE_URL = f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"


WELCOME_MESSAGE = (
    "**Xin chào, tôi là Meddy!** 🤗\n"
    "Tôi ở đây để giúp bạn giải quyết, tra cứu các thông tin trong lĩnh vực y tế. "
    "Hãy cứ thoải mái hỏi tôi bất cứ điều gì về y tế, và tôi sẽ làm hết sức mình để hỗ trợ bạn!"
)

AUTHENTICATED_SIDEBAR_GUIDE = (
    """
### 💡 Hướng dẫn sử dụng
    - "Triệu chứng của bệnh tiểu đường là gì?"
    - "Làm thế nào để phòng ngừa cảm cúm?"
"""
)

@cl.oauth_callback
def oauth_callback(provider_id, token, raw_user_data, default_user):
    if provider_id == "github":
        # Nếu email không có, lấy từ endpoint khác
        email = raw_user_data.get("email")
        if not email:
            import requests
            headers = {"Authorization": f"token {token}"}
            emails = requests.get("https://api.github.com/user/emails", headers=headers).json()
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
                "role": "user"
            }
        )

    elif provider_id == "google":
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
                "role": "user"
            }
        )

    return default_user


@cl.on_chat_start
async def start():
    msg = await cl.Message(content="Hỏi đáp y khoa với Meddy 🤓", author="system").send()

    # Gửi thêm hướng dẫn
    guide_msg = await cl.Message(content=AUTHENTICATED_SIDEBAR_GUIDE, author="system").send()


# Thêm handler cho tin nhắn từ user
@cl.on_message
async def main(message: cl.Message):
    # Kiểm tra user đã đăng nhập
    user = cl.user_session.get("user")
    if not user:
        await cl.Message(
            content="❌ Vui lòng đăng nhập để sử dụng tính năng này.",
            author="system"
        ).send()
        return

    # Xử lý tin nhắn từ user đã đăng nhập
    user_message = message.content

    # Tạo response message
    response_message = cl.Message(content="", author="Meddy")
    await response_message.send()

    try:
        # Gọi streaming response generator
        async for chunk in streaming_response_generator(user_message):
            await response_message.stream_token(chunk)
    except Exception as e:
        await response_message.stream_token(f"\n\n❌ Đã có lỗi xảy ra: {str(e)}")

    await response_message.update()


@cl.data_layer
def get_data_layer():
    return SQLAlchemyDataLayer(conninfo=DATABASE_URL)


@cl.on_chat_resume
async def on_chat_resume(thread: ThreadDict):
    cl.user_session.set("chat_history", [])

    for message in thread["steps"]:
        if message["type"] == "user_message":
            cl.user_session.get("chat_history").append(
                {"role": "user", "content": message["ouput"]}
            )
        elif message["type"] == "assistant_message":
            cl.user_session.get("chat_history").append(
                {"role": "assistant", "content": message["output"]}
            )

# Handle user status toggle actions
@cl.action_callback
async def handle_toggle_user(action):
    if action.name.startswith("toggle_user_"):
        username = action.payload["username"]
        current_status = action.payload["current_status"]
        new_status = not current_status

        # Refresh dashboard
        await show_dashboard()
