import os
from functools import lru_cache

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings

from .prompt_templates import (INTENT_DETECTION_PROMPT, RAG_PROMPT,
                               REWRITE_USER_PROMPT, SYSTEM_PROMPT)

load_dotenv()


class BackendSettings(BaseSettings):
    app_name: str = Field(default="Vietnamese Medical RAG QA System")
    app_version: str = Field(default="0.1.0")
    admin_email: str = Field(default="quann1906@gmail.com")

    # API Keys & Authentication (FR-065: Required env vars)
    openai_api_key: str = Field(default=os.getenv("OPENAI_API_KEY", ""))
    deepseek_api_key: str = Field(default=os.getenv("DEEPSEEK_API_KEY", ""))
    cohere_api_key: str = Field(default=os.getenv("COHERE_API_KEY", ""))
    tavily_api_key: str = Field(default=os.getenv("TAVILY_API_KEY", ""))
    hf_token: str = Field(default=os.getenv("HF_TOKEN", ""))

    jwt_secret: str = Field(default=os.getenv("JWT_SECRET", "CHANGE_ME_INSECURE"))
    jwt_expiry_hours: int = Field(default=int(os.getenv("JWT_EXPIRY_HOURS", "24")))

    # Digital Ocean Spaces
    # do_spaces_endpoint: str = Field(default=os.getenv("DO_SPACES_ENDPOINT", "https://sgp1.digitaloceanspaces.com"))
    # do_spaces_key: str = Field(default=os.getenv("DO_SPACES_KEY", ""))
    # do_spaces_secret: str = Field(default=os.getenv("DO_SPACES_SECRET", ""))
    # do_spaces_bucket: str = Field(default=os.getenv("DO_SPACES_BUCKET", "medical-rag-prod"))
    # do_spaces_region: str = Field(default=os.getenv("DO_SPACES_REGION", "sgp1"))

    # Elasticsearch (BM25 keyword search)
    elasticsearch_host: str = Field(
        default=os.getenv("ELASTICSEARCH_HOST", "localhost")
    )
    elasticsearch_port: int = Field(
        default=int(os.getenv("ELASTICSEARCH_PORT", "9200"))
    )
    elasticsearch_user: str = Field(
        default=os.getenv("ELASTICSEARCH_USER", "elasticsearch")
    )
    elasticsearch_password: str = Field(
        default=os.getenv("ELASTICSEARCH_PASSWORD", "elasticsearchadmin")
    )
    elasticsearch_scheme: str = Field(default=os.getenv("ELASTICSEARCH_SCHEME", "http"))

    @property
    def elasticsearch_url(self) -> str:
        """Construct Elasticsearch connection URL"""
        if self.elasticsearch_user and self.elasticsearch_password:
            return f"{self.elasticsearch_scheme}://{self.elasticsearch_user}:{self.elasticsearch_password}@{self.elasticsearch_host}:{self.elasticsearch_port}"
        return f"{self.elasticsearch_scheme}://{self.elasticsearch_host}:{self.elasticsearch_port}"

    # vLLM Model Serving (custom generation model: Qwen3-4B-Instruct)
    vllm_host: str = Field(default=os.getenv("VLLM_HOST", "localhost"))
    vllm_port: int = Field(default=int(os.getenv("VLLM_PORT", "8000")))
    vllm_model: str = Field(
        default=os.getenv("VLLM_MODEL", "Qwen/Qwen3-4B-Instruct-2507")
    )

    @property
    def vllm_url(self) -> str:
        return f"http://{self.vllm_host}:{self.vllm_port}"

    # Triton Inference Server (multi-model serving: embedding, reranker, guardrail)
    triton_host: str = Field(default=os.getenv("TRITON_HOST", "localhost"))
    triton_http_port: int = Field(default=int(os.getenv("TRITON_HTTP_PORT", "8001")))
    triton_grpc_port: int = Field(default=int(os.getenv("TRITON_GRPC_PORT", "8002")))

    @property
    def triton_http_url(self) -> str:
        return f"http://{self.triton_host}:{self.triton_http_port}"

    @property
    def triton_grpc_url(self) -> str:
        return f"grpc://{self.triton_host}:{self.triton_grpc_port}"

    # Vector Database
    qdrant_host: str = Field(default=os.getenv("QDRANT_HOST", "qdrant_db"))
    qdrant_port: str = Field(default=os.getenv("QDRANT_PORT", "6333"))

    # Cache & Queue (Redis for embeddings cache, search cache, Celery broker)
    redis_host: str = Field(default=os.getenv("REDIS_HOST", "redis_db"))
    redis_port: str = Field(default=os.getenv("REDIS_PORT", "6379"))
    redis_db: str = Field(default=os.getenv("REDIS_DB", "0"))
    redis_password: str = Field(default=os.getenv("REDIS_PASSWORD", "redisadmin"))

    @property
    def redis_url(self) -> str:
        """Construct Redis connection URL with optional password"""
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}"
        return f"redis://{self.redis_host}:{self.redis_port}"

    celery_broker_url: str = Field(
        default=os.getenv("CELERY_BROKER_URL", "redis://redis_db:6379")
    )
    celery_result_backend: str = Field(
        default=os.getenv("CELERY_RESULT_BACKEND", "redis://redis_db:6379")
    )

    # LLM and embedding model settings
    openai_model: str = Field(default="gpt-4o-mini")
    openai_embedding_model: str = Field(default="text-embedding-3-small")
    deeseek_chat_model: str = Field(default="deepseek-chat")
    deeseek_reasoner_model: str = Field(default="deepseek-reasoner")
    deepseek_baseurl: str = Field(
        default=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    )
    cohere_rerank_model: str = Field(default="rerank-multilingual-v3.0")

    # Qwen3 models
    qwen3_llm: str = Field(default="Qwen/Qwen3-4B-Instruct-2507")
    qwen3_embedding_model: str = Field(default="Qwen/Qwen3-Embedding-0.6B")
    qwen3_rerank_model: str = Field(default="Qwen/Qwen3-Reranker-0.6B")
    qwen3_guard_model: str = Field(default="Qwen/Qwen3Guard-Gen-0.6B")

    # Prompt templates
    system_prompt: str = Field(default=SYSTEM_PROMPT)
    rag_prompt: str = Field(default=RAG_PROMPT)
    rewrite_prompt: str = Field(default=REWRITE_USER_PROMPT)
    intent_detection_prompt: str = Field(default=INTENT_DETECTION_PROMPT)

    temperature: float = Field(default=0.7)
    max_tokens: int = Field(default=4096)

    # Qdrant vector database configuration
    default_collection_name: str = Field(default="documents")
    vector_dimension: int = Field(default=1024)
    top_k: int = Field(default=20)

    # CHUNKING settings
    chunk_size: int = Field(default=512)
    chunk_overlap: int = Field(default=50)


class DatabaseSettings(BaseSettings):
    postgres_user: str = Field(default=os.getenv("POSTGRES_USER", "postgresadmin"))
    postgres_password: str = Field(
        default=os.getenv("POSTGRES_PASSWORD", "postgresadmin")
    )
    postgres_db_name: str = Field(default=os.getenv("POSTGRES_DB", "medical_rag_db"))
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
