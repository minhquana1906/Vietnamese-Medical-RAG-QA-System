import json
import os
from typing import Dict, List, Optional

import httpx
from loguru import logger
from openai import OpenAI

from ..configs.setup import get_backend_settings
from ..core.model_config import (
    get_generation_model,
    get_generation_fallback,
    get_vllm_url,
    get_vllm_api_key,
)

settings = get_backend_settings()


def get_vllm_client():
    """
    Get remote vLLM client from config.
    Generation model is served on remote server (not local).

    Note: Timeout calculation:
    - max_tokens=4096 @ 26 tokens/s = ~160 seconds generation
    - Input processing: ~10 seconds
    - Safety margin: +30 seconds
    - Total: 200 seconds minimum
    """
    try:
        vllm_url = get_vllm_url()
        vllm_api_key = get_vllm_api_key()

        client = OpenAI(
            api_key=vllm_api_key,
            base_url=f"{vllm_url}/v1",
            timeout=200.0,
        )
        logger.debug(f"Initialized remote vLLM client at {vllm_url}")
        return client
    except Exception as e:
        logger.error(f"Error initializing remote vLLM client: {e}")
        return None


def qwen3_chat_complete(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    use_fallback: bool = True,
) -> Optional[str]:
    """
    Generate chat completion using remote vLLM server with Qwen3-4B-Instruct-2507.

    Qwen Team Recommended Parameters:
    - Temperature: 0.7
    - TopP: 0.8
    - TopK: 20
    - MinP: 0
    - Max Tokens: 1024 (sufficient for medical responses, reduces timeout risk)

    Reference: https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507

    Args:
        messages: Chat messages in OpenAI format
        model: Model name (if None, uses config)
        temperature: Sampling temperature (default: 0.7)
        max_tokens: Max tokens to generate (default: 1024, medical responses typically 500-800 tokens)
        use_fallback: Enable OpenAI fallback if remote vLLM fails

    Note: Reduced max_tokens from 4096 → 1024 to prevent timeouts:
    - 1024 tokens @ 26 tokens/s = ~40s generation (safe)
    - 4096 tokens @ 26 tokens/s = ~160s generation (risky, causes retries)
    """
    # Use Qwen3 recommended parameters
    temperature = temperature if temperature is not None else 0.7
    max_tokens = max_tokens if max_tokens is not None else 1024  # Reduced from 4096

    # Get active model from config if not specified
    if model is None:
        model = get_generation_model()
        logger.debug(f"Using generation model: {model}")

    # Try remote vLLM server first
    try:
        client = get_vllm_client()
        if client:
            logger.debug(
                f"Calling Qwen3-4B via vLLM: temp={temperature}, max_tokens={max_tokens}"
            )

            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=0.8,  # Qwen3 recommendation
                # Note: vLLM may not support top_k and min_p yet
            )

            logger.debug(f"✅ Generated with remote vLLM: {model}")
            content: str = response.choices[0].message.content or ""
            logger.debug(f"Generated {len(content)} chars")
            return content
    except Exception as e:
        logger.warning(f"❌ Remote vLLM failed ({model}): {e}")

    # Fallback to OpenAI
    if use_fallback:
        fallback_model = get_generation_fallback()
        logger.info(f"🔄 Fallback to OpenAI: {fallback_model}")
        return openai_chat_complete(
            messages, temperature=temperature, max_tokens=max_tokens
        )

    return None


def check_vllm_health() -> bool:
    """Check health of remote vLLM server."""
    try:
        vllm_url = get_vllm_url()
        response = httpx.get(f"{vllm_url}/health", timeout=5.0)
        if response.status_code == 200:
            logger.debug(f"✅ Remote vLLM service is healthy: {vllm_url}")
            return True
        return False
    except Exception as e:
        logger.warning(f"❌ Remote vLLM health check failed: {e}")
        return False


# ============= LEGACY OPENAI FUNCTIONS =============


def get_openai_client():
    try:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set.")
        client = OpenAI(api_key=api_key)
        return client
    except Exception as e:
        logger.error(f"Error initializing OpenAI client: {e}")
        raise


def openai_generate_embedding(text, model=settings.openai_embedding_model):
    try:
        text = text.replace("\n", " ")
        client = get_openai_client()
        response = client.embeddings.create(
            input=text, model=model, dimensions=settings.vector_dimension
        )
        return response.data[0].embedding
    except Exception as e:
        logger.error(f"Error generating embedding for {text}: {e}")
        raise


def openai_chat_complete(
    messages,
    model=settings.openai_model,
    temperature=settings.temperature,
    max_tokens=settings.max_tokens,
) -> Optional[str]:
    try:
        client = get_openai_client()
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        content: Optional[str] = response.choices[0].message.content
        return content
    except Exception as e:
        logger.error(f"Error generating response: {e}")
        raise


def generate_conversation_text(conversations):
    try:
        conversation_text = ""
        for conversation in conversations:
            if conversation.get("role") in ["user", "assistant"]:
                role = conversation.get("role")
                content = conversation.get("content", "")
                conversation_text += f"{role}: {content}\n"
        return conversation_text
    except Exception as e:
        logger.error(f"Error generating conversation text: {e}")
        raise


# rewrite user question based on history and user msg
def enhance_query_quality(history, message):
    """
    Enhance user query quality by rephrasing with conversation context.
    Uses Qwen3 generation model.
    """
    try:
        history_messages = generate_conversation_text(history)
        enhanced_prompt = settings.rewrite_prompt.format(
            history_messages=history_messages, message=message
        )
        logger.debug(f"Enhancing query with context (history length={len(history)})")

        messages = [
            {
                "role": "system",
                "content": "You are an expert in rephrasing user questions.",
            },
            {"role": "user", "content": enhanced_prompt},
        ]

        # Use Qwen3 for query enhancement
        enhanced_query = qwen3_chat_complete(messages, use_fallback=True)
        logger.debug(f"Enhanced query: {enhanced_query[:80]}...")
        return (
            enhanced_query if enhanced_query else message
        )  # Fallback to original message
    except Exception as e:
        logger.error(f"Error rewriting user question: {e}")
        return message  # Fallback to original on error


def detect_route(history, message):
    """
    Detect conversation route (medical vs general).
    Uses Qwen3 generation model.
    """
    try:
        logger.debug(f"Detecting route (history length={len(history)})")

        user_prompt = settings.intent_detection_prompt.format(
            history=history,
            message=message,
        )

        messages = [
            {
                "role": "system",
                "content": "You are an expert in classifying user intents.",
            },
            {"role": "user", "content": user_prompt},
        ]

        # Use Qwen3 for route detection
        route = qwen3_chat_complete(messages, use_fallback=True)
        logger.info(f"🎯 Route detected: {route}")
        return route if route else "medical"  # Default to medical route
    except Exception as e:
        logger.error(f"Error detecting route: {e}")
        return "medical"  # Default fallback


def get_tavily_agent_answer(messages):
    """
    Generate answer using Tavily web search with intelligent context management.

    Args:
        messages: Conversation history

    Returns:
        Generated response with citations

    Note: Automatically summarizes long conversation history to prevent vLLM context overflow
    """
    try:
        from ..functions.web_search import functions_info, tavily_search
        from .summarizer import summarize_old_messages

        logger.info("🔍 Using web search for additional context...")
        client = get_openai_client()

        # First, call the function to determine search query
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            functions=functions_info,
            function_call={"name": "tavily_search"},
        )

        # Extract search arguments
        args = json.loads(response.choices[0].message.function_call.arguments)
        logger.debug(f"Search query: {args}")

        # Perform web search (content is truncated in tavily_search function)
        observation = tavily_search(**args)
        logger.debug(f"Web search returned {len(observation)} chars")

        # INTELLIGENT CONTEXT MANAGEMENT:
        # Instead of hard truncation, summarize old messages if conversation is too long
        # Target budget: ~1500 tokens for history (leaves room for search + generation)
        # - Search results: ~150 tokens (truncated in web_search.py)
        # - System prompt: ~200 tokens
        # - Generation: ~4096 tokens
        # - History budget: ~1500 tokens (6000 chars)

        optimized_messages = summarize_old_messages(messages, target_tokens=1500)

        # Add search results to conversation context
        enhanced_messages = [
            *optimized_messages,
            {"role": "function", "name": "tavily_search", "content": observation},
            {
                "role": "user",
                "content": "Based on the search results above, please provide a comprehensive answer in Vietnamese. Remember to cite all sources with their URLs in the format 'Theo [Source Title]([URL]), ...' and include a 'Nguồn tham khảo:' section at the end.\n\n",
            },
        ]

        # Generate final response with citations using Qwen3
        final_response = qwen3_chat_complete(enhanced_messages, use_fallback=True)

        if not final_response:
            logger.error("Failed to generate web search response")
            return "Xin lỗi, không thể tạo câu trả lời từ kết quả tìm kiếm."

        logger.debug("Generated response with web search citations")

        return final_response
    except Exception as e:
        logger.error(f"Error in tavily agent answer: {e}")
        return f"Xin lỗi, đã có lỗi xảy ra khi tìm kiếm thông tin: {str(e)}"
