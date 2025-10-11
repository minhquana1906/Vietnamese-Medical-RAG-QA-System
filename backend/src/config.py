import os
from functools import lru_cache

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings

from .template import (INTENT_DETECTION_PROMPT, RAG_PROMPT,
                       REWRITE_USER_PROMPT, SYSTEM_PROMPT)

load_dotenv()


class BackendSettings(BaseSettings):
    app_name: str = Field(default="Vietnamese Medical RAG QA System")
    app_version: str = Field(default="0.1.0")
    admin_email: str = Field(default="quann1906@gmail.com")
    openai_api_key: str = Field(default=os.getenv("OPENAI_API_KEY", ""))
    cohere_api_key: str = Field(default=os.getenv("COHERE_API_KEY", ""))

    qdrant_host: str = Field(default=os.getenv("QDRANT_HOST", "qdrant_db"))
    qdrant_port: str = Field(default=os.getenv("QDRANT_PORT", "6333"))

    redis_host: str = Field(default=os.getenv("REDIS_HOST", "valkey_db"))
    redis_port: str = Field(default=os.getenv("REDIS_PORT", "6379"))

    celery_broker_url: str = Field(
        default=os.getenv("CELERY_BROKER_URL", "redis://valkey_db:6379")
    )
    celery_result_backend: str = Field(
        default=os.getenv("CELERY_RESULT_BACKEND", "redis://valkey_db:6379")
    )

    # LLM and embedding model settings
    openai_model: str = Field(default="gpt-4o-mini")
    openai_embedding_model: str = Field(default="text-embedding-3-small")
    cohere_rerank_model: str = Field(default="rerank-multilingual-v3.0")

    # Qwen3 models
    qwen3_llm: str = Field(default="Qwen/Qwen3-0.6B")
    qwen3_embedding_model: str = Field(default="Qwen/Qwen3-Embedding-0.6B")
    qwen3_rerank_model: str = Field(default="Qwen/Qwen3-Reranker-0.6B")

    # Prompt templates
    system_prompt: str = Field(default=SYSTEM_PROMPT)
    rag_prompt: str = Field(default=RAG_PROMPT)
    rewrite_prompt: str = Field(default=REWRITE_USER_PROMPT)
    intent_detection_prompt: str = Field(default=INTENT_DETECTION_PROMPT)

    temperature: float = Field(default=0.7)
    max_tokens: int = Field(default=2048)

    # Qdrant vector database configuration
    default_collection_name: str = Field(default="documents")
    vector_dimension: int = Field(default=1536)
    top_k: int = Field(default=5)

    # CHUNKING settings
    chunk_size: int = Field(default=512)
    chunk_overlap: int = Field(default=50)


class DatabaseSettings(BaseSettings):
    postgres_user: str = Field(default=os.getenv("POSTGRES_USER", "postgres_admin"))
    postgres_password: str = Field(
        default=os.getenv("POSTGRES_PASSWORD", "postgres_password")
    )
    postgres_db_name: str = Field(
        default=os.getenv("POSTGRES_DB", "chat_conversation_db")
    )
    postgres_host: str = Field(default=os.getenv("POSTGRES_HOST", "localhost"))
    postgres_port: str = Field(default=os.getenv("POSTGRES_PORT", "5432"))

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}@"
            f"{self.postgres_host}:{self.postgres_port}/{self.postgres_db_name}"
        )


@lru_cache
def get_backend_settings() -> BackendSettings:
    return BackendSettings()


@lru_cache
def get_database_settings() -> DatabaseSettings:
    return DatabaseSettings()
