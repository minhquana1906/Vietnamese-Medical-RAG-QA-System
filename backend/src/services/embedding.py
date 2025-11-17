from typing import List, Optional

import httpx
from loguru import logger

from ..configs.setup import get_backend_settings
from ..core.model_config import (
    get_embedding_model,
    get_embedding_fallback,
)

settings = get_backend_settings()


class Qwen3EmbeddingService:

    def __init__(
        self,
        local_url: str = "http://localhost:8000",
        openai_fallback: bool = True,
    ):
        """
        Initialize Qwen3 Embedding Service with local FastAPI backend.

        Args:
            local_url: Local backend URL
            openai_fallback: Enable OpenAI fallback if local fails
        """
        self.local_url = local_url
        self.huggingface_model = get_embedding_model()

        logger.debug(
            f"Init Qwen3EmbeddingService: Local={local_url}, Model={self.huggingface_model}"
        )

        self.openai_fallback = openai_fallback
        self.client = httpx.Client(timeout=30.0)
        self.openai_client = None

        if self.openai_fallback:
            try:
                from openai import OpenAI

                self.openai_client = OpenAI(api_key=settings.openai_api_key)
                logger.debug(f"OpenAI fallback enabled: {get_embedding_fallback()}")
            except ImportError:
                logger.warning("OpenAI library not available, fallback disabled")
                self.openai_fallback = False

    def embed_text(self, text: str, use_cache: bool = True) -> Optional[List[float]]:
        # Check cache first
        if use_cache:
            from ..core.cache import get_query_embedding

            cached_embedding = get_query_embedding(text)
            if cached_embedding:
                return cached_embedding

        # Try local inference
        embedding = self._embed_with_local([text])
        if embedding:
            embedding = embedding[0]

        # Fallback to OpenAI if local fails
        if embedding is None and self.openai_fallback:
            logger.warning("Local embedding failed, falling back to OpenAI")
            embedding = self._embed_with_openai(text)

        # Cache result if successful
        if embedding and use_cache:
            from ..core.cache import cache_query_embedding

            cache_query_embedding(text, embedding)

        return embedding

    def embed_batch(
        self, texts: List[str], batch_size: int = 32, use_cache: bool = False
    ) -> List[Optional[List[float]]]:
        embeddings = []

        # Process in batches
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            batch_embeddings = self._embed_with_local(batch)

            # Fallback for failed embeddings
            if batch_embeddings is None and self.openai_fallback:
                logger.warning(f"Local failed for batch {i}, using OpenAI fallback")
                batch_embeddings = [self._embed_with_openai(text) for text in batch]

            embeddings.extend(batch_embeddings or [None] * len(batch))

        logger.debug(f"Generated {len(texts)} embeddings (batch size: {batch_size})")
        return embeddings

    def _embed_with_local(self, texts: List[str]) -> Optional[List[List[float]]]:
        """Call local FastAPI endpoint"""
        try:
            payload = {"texts": texts, "normalize": True}

            response = self.client.post(
                f"{self.local_url}/v1/models/embed",
                json=payload,
            )

            if response.status_code == 200:
                result = response.json()
                embeddings: List[List[float]] = result["embeddings"]
                logger.debug(f"Local embedding generated for {len(texts)} texts")
                return embeddings
            else:
                logger.error(
                    f"Local embedding failed: {response.status_code} - {response.text}"
                )
                return None
        except Exception as e:
            logger.error(f"Error calling local embedding: {e}")
            return None

    def _embed_with_openai(self, text: str) -> Optional[List[float]]:
        if not self.openai_client:
            return None

        try:
            fallback_model = get_embedding_fallback()
            response = self.openai_client.embeddings.create(
                model=fallback_model,
                input=text,
                dimensions=settings.vector_dimension,
            )
            embedding = response.data[0].embedding
            logger.debug(
                f"OpenAI embedding generated (model={fallback_model}): {text[:50]}..."
            )
            return embedding
        except Exception as e:
            logger.error(f"Error calling OpenAI for embedding: {e}")
            return None

    def get_embedding_dimension(self) -> int:
        return settings.vector_dimension

    def health_check(self) -> bool:
        try:
            response = self.client.get(f"{self.local_url}/v1/ready")
            if response.status_code == 200:
                logger.info("Local embedding service is healthy")
                return True
            else:
                logger.warning(f"Local health check failed: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"Error checking local health: {e}")
            return False


_embedding_service_instance = None


def get_embedding_service() -> Qwen3EmbeddingService:
    global _embedding_service_instance
    if _embedding_service_instance is None:
        _embedding_service_instance = Qwen3EmbeddingService()
    return _embedding_service_instance
