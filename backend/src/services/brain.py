import json
import os
from typing import Dict, List, Optional

import httpx
from loguru import logger
from openai import OpenAI

from ..configs.setup import get_backend_settings
from ..core.model_config import (
    get_generation_model,
    get_vllm_url,
    get_vllm_api_key,
)

settings = get_backend_settings()


def get_vllm_client():
    """Get remote vLLM client from config."""
    try:
        vllm_url = get_vllm_url()
        vllm_api_key = get_vllm_api_key()

        client = OpenAI(
            api_key=vllm_api_key,
            base_url=f"{vllm_url}/v1",
            timeout=200.0,
        )
        return client
    except Exception as e:
        logger.error(f"[GEN] vLLM client init failed: {e}")
        return None


def qwen3_chat_complete(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> Optional[str]:
    """Generate chat completion using remote vLLM server with Qwen3-4B-Instruct-2507."""
    temperature = temperature if temperature is not None else 0.7
    max_tokens = max_tokens if max_tokens is not None else 2048

    if model is None:
        model = get_generation_model()

    try:
        client = get_vllm_client()
        if client:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=0.8,
            )
            content: str = response.choices[0].message.content or ""
            return content
    except Exception as e:
        error_msg = str(e)
        if "<!DOCTYPE html>" in error_msg or "<html" in error_msg:
            error_msg = "vLLM service is loading"
        logger.warning(f"[GEN] vLLM failed: {error_msg}")

    return None


def check_vllm_health() -> bool:
    """Check health of remote vLLM server."""
    try:
        vllm_url = get_vllm_url()
        response = httpx.get(f"{vllm_url}/version", timeout=5.0)
        return response.status_code == 200
    except Exception:
        return False


def get_openai_client():
    try:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set.")
        client = OpenAI(api_key=api_key)
        return client
    except Exception as e:
        logger.error(f"[GEN] OpenAI client init failed: {e}")
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
        logger.error(f"[GEN] Conversation text generation failed: {e}")
        raise


def enhance_query_quality(history, message):
    """Enhance user query quality by rephrasing with conversation context."""
    try:
        history_messages = generate_conversation_text(history)
        enhanced_prompt = settings.rewrite_prompt.format(
            history_messages=history_messages, message=message
        )

        messages = [
            {
                "role": "system",
                "content": "You are an expert in rephrasing user questions.",
            },
            {"role": "user", "content": enhanced_prompt},
        ]

        enhanced_query = qwen3_chat_complete(messages)
        return enhanced_query if enhanced_query else message
    except Exception as e:
        logger.error(f"[GEN] Query enhancement failed: {e}")
        return message


def detect_route(history, message):
    """Detect conversation route (medical vs general)."""
    try:
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

        route = qwen3_chat_complete(messages)
        return route if route else "medical"
    except Exception as e:
        logger.error(f"[GEN] Route detection failed: {e}")
        return "medical"


def get_tavily_agent_answer(messages):
    """Generate answer using Tavily web search with intelligent context management."""
    try:
        from ..functions.web_search import functions_info, tavily_search
        from .summarizer import summarize_old_messages

        client = get_openai_client()

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            functions=functions_info,
            function_call={"name": "tavily_search"},
        )

        args = json.loads(response.choices[0].message.function_call.arguments)
        observation = tavily_search(**args)
        optimized_messages = summarize_old_messages(messages, target_tokens=1500)

        enhanced_messages = [
            *optimized_messages,
            {"role": "function", "name": "tavily_search", "content": observation},
            {
                "role": "user",
                "content": "Based on the search results above, please provide a comprehensive answer in Vietnamese. Remember to cite all sources with their URLs in the format 'Theo [Source Title]([URL]), ...' and include a 'Nguồn tham khảo:' section at the end.\n\n",
            },
        ]

        final_response = qwen3_chat_complete(enhanced_messages, max_tokens=1536)

        if not final_response:
            return "Xin lỗi, không thể tạo câu trả lời từ kết quả tìm kiếm."

        return final_response
    except Exception as e:
        logger.error(f"[GEN] Tavily agent failed: {e}")
        return f"Xin lỗi, đã có lỗi xảy ra khi tìm kiếm thông tin: {str(e)}"
