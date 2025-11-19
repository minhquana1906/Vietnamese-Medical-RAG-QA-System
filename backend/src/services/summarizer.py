from hashlib import md5
from typing import Optional

from loguru import logger

from ..core.cache import get_cached_value, set_cached_value
from .brain import qwen3_chat_complete


MESSAGE_COUNT_THRESHOLD = 8  # Trigger summary when conversation exceeds this count
TOKEN_BUDGET_DEFAULT = 1500  # Default token budget for conversation history
RECENT_MESSAGES_TO_KEEP = 2  # Always keep last N messages without summarization

# Token estimation (Vietnamese/English mix)
CHARS_PER_TOKEN = 4  # ~4 chars = 1 token for mixed language


def estimate_tokens(text: str) -> int:
    """
    Estimate token count from text length.

    Vietnamese text typically has higher char-to-token ratio than English.
    Using conservative estimate: 4 chars ≈ 1 token

    Args:
        text: Input text

    Returns:
        Estimated token count
    """
    return len(text) // CHARS_PER_TOKEN


def calculate_messages_tokens(messages: list[dict]) -> int:
    """
    Calculate total tokens in a list of messages.

    Args:
        messages: List of message dicts with 'content' field

    Returns:
        Total estimated tokens
    """
    total_text = "".join([m.get("content", "") for m in messages])
    return estimate_tokens(total_text)


def get_summarized_content(
    text: str, max_tokens: int = 512, use_cache: bool = True
) -> str:
    """
    Summarize text content using Qwen3 generation model with caching.

    Args:
        text: Content to summarize
        max_tokens: Maximum tokens for summary output
        use_cache: Enable Redis caching (default: True)

    Returns:
        Summarized text

    Note: Uses Qwen3-4B-Instruct for fast, high-quality Vietnamese summaries
    """
    if not text or not text.strip():
        return text

    # Check cache first
    if use_cache:
        cache_key = f"summary:{md5(text.encode()).hexdigest()}"
        cached_summary = get_cached_value(cache_key)
        if cached_summary:
            logger.debug("✅ Using cached summary")
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
            temperature=0.3,  # Lower temperature for focused summaries
            max_tokens=max_tokens,
            use_fallback=False,  # No fallback for summarization
        )

        if not summary:
            logger.warning("Failed to generate summary, returning original text")
            return text

        # Cache the result (expire after 1 hour)
        if use_cache:
            set_cached_value(cache_key, summary, expiration=3600)

        logger.debug(f"Summarized {len(text)} chars → {len(summary)} chars")
        return summary

    except Exception as e:
        logger.error(f"Error summarizing text: {e}")
        return text  # Fallback to original


def should_auto_summarize(messages: list[dict]) -> bool:
    """
    Determine if conversation should be auto-summarized.

    Triggers summarization when:
    1. Message count exceeds threshold (8+ messages)
    2. Token count exceeds budget (1500+ tokens)

    Args:
        messages: Full conversation history

    Returns:
        True if summarization is needed
    """
    message_count = len(messages)
    token_count = calculate_messages_tokens(messages)

    # Check message count threshold
    if message_count > MESSAGE_COUNT_THRESHOLD:
        logger.debug(
            f"Auto-summary triggered: {message_count} messages > {MESSAGE_COUNT_THRESHOLD}"
        )
        return True

    # Check token budget threshold
    if token_count > TOKEN_BUDGET_DEFAULT:
        logger.debug(
            f"Auto-summary triggered: ~{token_count} tokens > {TOKEN_BUDGET_DEFAULT}"
        )
        return True

    return False


def summarize_old_messages(
    messages: list[dict],
    target_tokens: Optional[int] = None,
    force_summarize: bool = False,
) -> list[dict]:
    """
    Intelligently summarize old messages with auto-detection.

    Strategy:
    1. Auto-detect if summarization is needed (message count or token budget)
    2. Keep last N messages as-is (most relevant context)
    3. Summarize older messages into a single system message
    4. Use caching to avoid re-summarizing same content

    Args:
        messages: Full conversation history
        target_tokens: Target token budget (default: 1500)
        force_summarize: Force summarization even if below threshold

    Returns:
        Optimized message list with summarized history

    Example:
        Input: [sys, msg1, msg2, msg3, msg4, msg5, msg6, msg7, msg8] (9 messages)
        Output: [sys, summary_of_msg1-5, msg6, msg7, msg8] (5 messages)
    """
    if not messages:
        return messages

    target_tokens = target_tokens or TOKEN_BUDGET_DEFAULT

    # Separate system message from conversation
    system_messages = [m for m in messages if m.get("role") == "system"]
    conversation_messages = [m for m in messages if m.get("role") != "system"]

    # Check if summarization is needed
    if not force_summarize and not should_auto_summarize(conversation_messages):
        logger.debug(
            f"No summarization needed: {len(conversation_messages)} messages, ~{calculate_messages_tokens(conversation_messages)} tokens"
        )
        return messages

    # Minimum messages required for summarization
    if len(conversation_messages) <= RECENT_MESSAGES_TO_KEEP:
        logger.debug("Too few messages for summarization")
        return messages

    # Split into old and recent messages
    recent_messages = conversation_messages[-RECENT_MESSAGES_TO_KEEP:]
    old_messages = conversation_messages[:-RECENT_MESSAGES_TO_KEEP]

    # Calculate token budgets
    recent_tokens = calculate_messages_tokens(recent_messages)
    system_tokens = calculate_messages_tokens(system_messages)
    available_tokens = target_tokens - recent_tokens - system_tokens - 100  # Buffer

    if available_tokens < 200:
        logger.warning(
            f"Insufficient token budget ({available_tokens}), keeping only recent messages"
        )
        return system_messages + recent_messages

    # Build conversation text from old messages
    conversation_parts = []
    for msg in old_messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if content:  # Skip empty messages
            conversation_parts.append(f"[{role.upper()}]: {content}")

    if not conversation_parts:
        return messages

    old_conversation_text = "\n\n".join(conversation_parts)
    old_tokens = estimate_tokens(old_conversation_text)

    logger.info(
        f"📝 Summarizing {len(old_messages)} old messages (~{old_tokens} tokens) → target ~{min(available_tokens, 512)} tokens"
    )

    # Summarize old messages with caching
    summary = get_summarized_content(
        old_conversation_text,
        max_tokens=min(available_tokens, 512),  # Cap at 512 tokens
        use_cache=True,  # Enable caching
    )

    # Build optimized message list
    summarized_messages = [
        *system_messages,
        {
            "role": "system",
            "content": f"📋 Tóm tắt {len(old_messages)} tin nhắn trước:\n{summary}",
        },
        *recent_messages,
    ]

    # Verify optimization
    new_tokens = calculate_messages_tokens(summarized_messages)
    compression_ratio = (
        (1 - new_tokens / (old_tokens + recent_tokens + system_tokens)) * 100
        if (old_tokens + recent_tokens + system_tokens) > 0
        else 0
    )

    logger.info(
        f"✅ Summary complete: {len(messages)} → {len(summarized_messages)} messages | "
        f"~{old_tokens + recent_tokens + system_tokens} → ~{new_tokens} tokens | "
        f"Reduced {compression_ratio:.1f}%"
    )

    return summarized_messages
