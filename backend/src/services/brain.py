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
)

settings = get_backend_settings()


def get_remote_vllm_client():
    """
    Get remote vLLM client from config.
    Generation model is served on remote server (not local).
    """
    try:
        vllm_url = get_vllm_url()
        client = OpenAI(
            api_key=os.getenv("REMOTE_VLLM_API_KEY"),
            base_url=f"{vllm_url}/v1",
            timeout=30.0,
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
    Generate chat completion using remote vLLM server.
    Generation model is served on external server (config: serving.vllm_url).

    Args:
        messages: Chat messages in OpenAI format
        model: Model name (if None, uses config)
        temperature: Sampling temperature
        max_tokens: Max tokens to generate
        use_fallback: Enable OpenAI fallback if remote vLLM fails
    """
    temperature = temperature if temperature is not None else settings.temperature
    max_tokens = max_tokens if max_tokens is not None else settings.max_tokens

    # Get active model from config if not specified
    if model is None:
        model = get_generation_model()
        logger.debug(f"Using generation model: {model}")

    # Try remote vLLM server first
    try:
        client = get_remote_vllm_client()
        if client:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            logger.debug(f"✅ Generated with remote vLLM: {model}")
            content: str = response.choices[0].message.content or ""
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


def check_remote_vllm_health() -> bool:
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
    try:
        from ..functions.web_search import functions_info, tavily_search

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

        # Perform web search
        observation = tavily_search(**args)
        logger.debug(f"Web search returned {len(observation)} chars")

        # Add search results to conversation context
        enhanced_messages = [
            *messages,
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
