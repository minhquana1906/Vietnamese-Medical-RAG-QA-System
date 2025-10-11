import json
import os

from loguru import logger
from openai import OpenAI

from .config import get_backend_settings

settings = get_backend_settings()


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
            input=text,
            model=model,
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
):
    try:
        client = get_openai_client()
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.choices[0].message.content
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
    try:
        history_messages = generate_conversation_text(history)
        enhanced_prompt = settings.rewrite_prompt.format(
            history_messages=history_messages, message=message
        )
        logger.info(f"Rewrote user's prompt: {enhanced_prompt}")

        openai_messages = [
            {
                "role": "system",
                "content": "You are an expert in rephrasing user questions.",
            },
            {"role": "user", "content": enhanced_prompt},
        ]
        logger.info(f"Rephrase input messages: {openai_messages}")

        return openai_chat_complete(openai_messages)
    except Exception as e:
        logger.error(f"Error rewriting user question: {e}")
        raise


def detect_route(history, message):
    try:
        logger.info(f"Detect route on history messages: {history}")

        user_prompt = settings.intent_detection_prompt.format(
            history=history,
            message=message,
        )

        openai_messages = [
            {
                "role": "system",
                "content": "You are an expert in classifying user intents.",
            },
            {"role": "user", "content": user_prompt},
        ]
        logger.info(f"Route output: {openai_messages}")
        return openai_chat_complete(openai_messages)
    except Exception as e:
        logger.error(f"Error detecting route: {e}")
        raise


def get_tavily_agent_answer(messages):
    try:
        from .functions.web_search import functions_info, tavily_search

        logger.info("Calling tavily tool search for additional information...")
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
        logger.info(f"Search query args: {args}")

        # Perform web search
        observation = tavily_search(**args)
        logger.info(f"Web search results obtained with {len(observation)} characters")

        # Add search results to conversation context
        enhanced_messages = [
            *messages,
            {"role": "function", "name": "tavily_search", "content": observation},
            {
                "role": "user",
                "content": "Based on the search results above, please provide a comprehensive answer in Vietnamese. Remember to cite all sources with their URLs in the format 'Theo [Source Title]([URL]), ...' and include a 'Nguồn tham khảo:' section at the end.\n\n",
            },
        ]

        # Generate final response with citations
        final_response = openai_chat_complete(enhanced_messages)
        logger.info("Generated response with web search citations")

        return final_response
    except Exception as e:
        logger.error(f"Error in tavily agent answer: {e}")
        raise
