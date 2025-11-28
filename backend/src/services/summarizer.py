from hashlib import md5
from typing import Optional

from loguru import logger

from ..core.cache import get_cached_value, set_cached_value
from .brain import qwen3_chat_complete

MESSAGE_COUNT_THRESHOLD = 8
TOKEN_BUDGET_DEFAULT = 1500
RECENT_MESSAGES_TO_KEEP = 2
CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """Estimate token count from text length."""
    return len(text) // CHARS_PER_TOKEN


def calculate_messages_tokens(messages: list[dict]) -> int:
    """Calculate total tokens in a list of messages."""
    total_text = "".join([m.get("content", "") for m in messages])
    return estimate_tokens(total_text)


def get_summarized_content(
    text: str, max_tokens: int = 512, use_cache: bool = True
) -> str:
    """Summarize text content using Qwen3 generation model with caching."""
    if not text or not text.strip():
        return text

    if use_cache:
        cache_key = f"summary:{md5(text.encode()).hexdigest()}"
        cached_summary = get_cached_value(cache_key)
        if cached_summary:
            return cached_summary

    try:
        messages = [
            {
                "role": "system",
                "content": "Bạn là trợ lý AI chuyên tóm tắt nội dung. Nhiệm vụ: tạo bản tóm tắt ngắn gọn, giữ lại thông tin quan trọng nhất.",
            },
            {
                "role": "user",
                "content": f"Tóm tắt cuộc hội thoại sau, giữ lại thông tin chính:\n\n{text}\n\nTóm tắt:",
            },
        ]

        summary = qwen3_chat_complete(
            messages,
            temperature=0.3,
            max_tokens=max_tokens,
        )

        if not summary:
            return text

        if use_cache:
            set_cached_value(cache_key, summary, expiration=3600)

        return summary

    except Exception as e:
        logger.error(f"[SUMMARY] Error: {e}")
        return text


def should_auto_summarize(messages: list[dict]) -> bool:
    """Determine if conversation should be auto-summarized."""
    message_count = len(messages)
    token_count = calculate_messages_tokens(messages)

    if message_count > MESSAGE_COUNT_THRESHOLD:
        return True

    if token_count > TOKEN_BUDGET_DEFAULT:
        return True

    return False


def summarize_old_messages(
    messages: list[dict],
    target_tokens: Optional[int] = None,
    force_summarize: bool = False,
) -> list[dict]:
    """Intelligently summarize old messages with auto-detection."""
    if not messages:
        return messages

    target_tokens = target_tokens or TOKEN_BUDGET_DEFAULT

    system_messages = [m for m in messages if m.get("role") == "system"]
    conversation_messages = [m for m in messages if m.get("role") != "system"]

    if not force_summarize and not should_auto_summarize(conversation_messages):
        return messages

    if len(conversation_messages) <= RECENT_MESSAGES_TO_KEEP:
        return messages

    recent_messages = conversation_messages[-RECENT_MESSAGES_TO_KEEP:]
    old_messages = conversation_messages[:-RECENT_MESSAGES_TO_KEEP]

    recent_tokens = calculate_messages_tokens(recent_messages)
    system_tokens = calculate_messages_tokens(system_messages)
    available_tokens = target_tokens - recent_tokens - system_tokens - 100

    if available_tokens < 200:
        return system_messages + recent_messages

    conversation_parts = []
    for msg in old_messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if content:
            conversation_parts.append(f"[{role.upper()}]: {content}")

    if not conversation_parts:
        return messages

    old_conversation_text = "\n\n".join(conversation_parts)

    summary = get_summarized_content(
        old_conversation_text,
        max_tokens=min(available_tokens, 512),
        use_cache=True,
    )

    summarized_messages = [
        *system_messages,
        {
            "role": "system",
            "content": f"📋 Tóm tắt {len(old_messages)} tin nhắn trước:\n{summary}",
        },
        *recent_messages,
    ]

    return summarized_messages
