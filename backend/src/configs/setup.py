import os
from functools import lru_cache

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings

from .prompt_templates import (
    INTENT_DETECTION_PROMPT,
    RAG_PROMPT,
    REWRITE_USER_PROMPT,
    SPEECH_RAG_PROMPT,
    SPEECH_RAG_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
)

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

    # TTS Configuration (ElevenLabs)
    elevenlabs_api_key: str = Field(default=os.getenv("ELEVENLABS_API_KEY", ""))
    elevenlabs_voice_id: str = Field(
        default=os.getenv("ELEVENLABS_VOICE_ID", "A5w1fw5x0uXded1LDvZp")
    )
    elevenlabs_model_id: str = Field(
        default=os.getenv("ELEVENLABS_MODEL_ID", "eleven_v3")
    )
    elevenlabs_stability: float = Field(
        default=float(os.getenv("ELEVENLABS_STABILITY", "0.5"))
    )
    elevenlabs_similarity_boost: float = Field(
        default=float(os.getenv("ELEVENLABS_SIMILARITY_BOOST", "0.75"))
    )
    elevenlabs_speed: float = Field(default=float(os.getenv("ELEVENLABS_SPEED", "1.0")))

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
    vllm_host: str = Field(default=os.getenv("VLLM_HOST", "vllm"))
    vllm_port: int = Field(default=int(os.getenv("VLLM_PORT", "8001")))
    vllm_model: str = Field(
        default=os.getenv("VLLM_MODEL", "Qwen/Qwen3-4B-Instruct-2507")
    )

    @property
    def vllm_url(self) -> str:
        return f"http://{self.vllm_host}:{self.vllm_port}"

    # Backend API (for embedding/rerank/guardrails models served by FastAPI)
    backend_api_host: str = Field(default=os.getenv("BACKEND_API_HOST", "chatbot_api"))
    backend_api_port: int = Field(default=int(os.getenv("BACKEND_API_PORT", "8000")))

    @property
    def backend_api_url(self) -> str:
        return f"http://{self.backend_api_host}:{self.backend_api_port}"

    # Qwen3 Models GPU Service (NEW: separate GPU service for optimal performance)
    qwen3_models_url: str = Field(
        default=os.getenv("QWEN3_MODELS_URL", "http://qwen3_models:8002")
    )
    qwen3_models_enabled: bool = Field(
        default=os.getenv("QWEN3_MODELS_ENABLED", "true").lower() == "true"
    )

    # Guardrails Configuration (can be disabled for load testing)
    guardrails_enabled: bool = Field(
        default=os.getenv("GUARDRAILS_ENABLED", "true").lower() == "true"
    )

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

    # Monitoring & Observability
    tempo_endpoint: str = Field(
        default=os.getenv("TEMPO_ENDPOINT", "http://tempo:4317")
    )
    tempo_enabled: bool = Field(
        default=os.getenv("TEMPO_ENABLED", "true").lower() == "true"
    )

    # LLM and embedding model settings
    openai_model: str = Field(default="gpt-4o-mini")
    openai_embedding_model: str = Field(default="text-embedding-3-small")
    deeseek_chat_model: str = Field(default="deepseek-chat")
    deeseek_reasoner_model: str = Field(default="deepseek-reasoner")
    deepseek_baseurl: str = Field(
        default=os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com")
    )
    cohere_rerank_model: str = Field(default="rerank-v3.5")

    # Qwen3 models
    qwen3_llm: str = Field(default="Qwen/Qwen3-4B-Instruct-2507")
    qwen3_embedding_model: str = Field(default="Qwen/Qwen3-Embedding-0.6B")
    qwen3_rerank_model: str = Field(default="Qwen/Qwen3-Reranker-0.6B")
    qwen3_guard_model: str = Field(default="Qwen/Qwen3Guard-Gen-0.6B")

    # Prompt templates
    system_prompt: str = Field(default=SYSTEM_PROMPT)
    rag_prompt: str = Field(default=RAG_PROMPT)
    speech_rag_system_prompt: str = Field(default=SPEECH_RAG_SYSTEM_PROMPT)
    speech_rag_prompt: str = Field(default=SPEECH_RAG_PROMPT)

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

    # Logging settings
    log_level: str = Field(default=os.getenv("LOG_LEVEL", "INFO"))
    debug: bool = Field(default=os.getenv("DEBUG", "false").lower() == "true")


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
