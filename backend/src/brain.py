import os

from llama_index.embeddings.huggingface import HuggingFaceEmbedding
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


# openai embedding
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


# oss embedding
def oss_generate_embedding(text, model=settings.oss_embedding_model):
    try:
        text = text.replace("\n", " ")
        model = HuggingFaceEmbedding(model_name=model, trust_remote_code=True)
        response = model.get_text_embedding(text)
        return response
    except Exception as e:
        logger.error(f"Error generating embedding for {text}: {e}")
        raise


# openai chat completion
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


# oss llm chat complete
def qwen3_chat_complete(
    messages,
    model=settings.qwen3_llm,
    temperature=settings.qwen3_temperature,
    top_k=settings.qwen3_top_k,
    top_p=settings.qwen3_top_p,
):
    # TODO: Serving Qwen3 via VLLM
    pass


def format_context(docs):
    try:
        context = ""
        for i, doc in enumerate(docs):
            context += f"Document {i + 1} (Confidence Score: {doc['score']}):\nTitle: {doc['title']}\nContent: {doc['content']}\n\n"
        return context
    except Exception as e:
        logger.error(f"Error structuring context: {e}")
        raise
