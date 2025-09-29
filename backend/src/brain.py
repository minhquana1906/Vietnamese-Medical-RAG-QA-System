import os

from loguru import logger
from openai import OpenAI

from .config import EMBEDDING_MODEL, LLM, MAX_TOKENS, TEMPERATURE


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


def openai_generate_embedding(text, model=EMBEDDING_MODEL):
    try:
        text = text.replace("\n", " ")
        client = get_openai_client()
        response = client.embeddings.create(
            input=text,
            model=model,
        )
        res = response.data[0].embedding
        logger.info(f"Generated embedding for {text}: {res[:10]}...")
        return res
    except Exception as e:
        logger.error(f"Error generating embedding for {text}: {e}")
        raise


def openai_chat_complete(
    messages, model=LLM, temperature=TEMPERATURE, max_tokens=MAX_TOKENS
):
    try:
        client = get_openai_client()
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        content = response.choices[0].message.content
        # logger.info(f"Generated response: {content}")
        return content
    except Exception as e:
        logger.error(f"Error generating response: {e}")
        raise


def format_context(docs):
    try:
        context = ""
        for i, doc in enumerate(docs):
            context += f"Đoạn văn bản {i + 1} (Điểm tin cậy: {doc['score']}):\nTiêu đề: {doc['title']}\nNội dung: {doc['content']}\n\n"
        return context
    except Exception as e:
        logger.error(f"Error structuring context: {e}")
        raise
