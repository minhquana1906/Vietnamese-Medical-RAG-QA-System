from typing import List, Optional, Union

import httpx
from loguru import logger

from ..configs.setup import get_backend_settings
from ..core.model_config import (
    get_embedding_model,
    get_embedding_triton_name,
    get_embedding_fallback,
    get_triton_http_url,
)

settings = get_backend_settings()


class Qwen3EmbeddingService:

    def __init__(
        self,
        triton_url: Optional[str] = None,
        model_name: Optional[str] = None,
        openai_fallback: bool = True,
    ):
        """
        Initialize Qwen3 Embedding Service with Triton backend.

        Args:
            triton_url: Triton server URL (if None, uses config)
            model_name: Triton model name (if None, uses config)
            openai_fallback: Enable OpenAI fallback if Triton fails
        """
        # Get config values
        self.triton_url = triton_url or get_triton_http_url()
        self.model_name = model_name or get_embedding_triton_name()
        self.huggingface_model = get_embedding_model()  # For logging

        logger.info(
            f"Initialized Qwen3EmbeddingService: "
            f"HF={self.huggingface_model}, Triton={self.model_name}"
        )

        self.openai_fallback = openai_fallback
        self.client = httpx.Client(timeout=30.0)
        self.openai_client = None
        if self.openai_fallback:
            try:
                from openai import OpenAI

                self.openai_client = OpenAI(api_key=settings.openai_api_key)
                fallback_model = get_embedding_fallback()
                logger.info(f"OpenAI fallback enabled: {fallback_model}")
            except ImportError:
                logger.warning("OpenAI library not available, fallback disabled")
                self.openai_fallback = False

    def embed_text(self, text: str, use_cache: bool = True) -> Optional[List[float]]:
        # Check cache first
        if use_cache:
            from ..core.cache import cache_query_embedding, get_query_embedding

            cached_embedding = get_query_embedding(text)
            if cached_embedding:
                return cached_embedding

        # Try Triton inference
        embedding = self._embed_with_triton(text)

        # Fallback to OpenAI if Triton fails
        if embedding is None and self.openai_fallback:
            logger.warning("Triton embedding failed, falling back to OpenAI")
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
            batch_embeddings = self._embed_batch_with_triton(batch)

            # Fallback for failed embeddings
            if self.openai_fallback:
                for j, emb in enumerate(batch_embeddings):
                    if emb is None:
                        logger.warning(
                            f"Triton failed for text {i + j}, using OpenAI fallback"
                        )
                        batch_embeddings[j] = self._embed_with_openai(batch[j])

            embeddings.extend(batch_embeddings)

        logger.info(
            f"Generated embeddings for {len(texts)} texts (batch size: {batch_size})"
        )
        return embeddings

    def _embed_with_triton(self, text: str) -> Optional[List[float]]:
        try:
            # Triton inference request format
            payload = {
                "inputs": [
                    {
                        "name": "input_text",
                        "shape": [1],
                        "datatype": "BYTES",
                        "data": [text],
                    }
                ]
            }

            response = self.client.post(
                f"{self.triton_url}/v2/models/{self.model_name}/infer",
                json=payload,
            )

            if response.status_code == 200:
                result = response.json()
                embedding: List[float] = result["outputs"][0]["data"]
                logger.debug(f"Triton embedding generated for text: {text[:50]}...")
                return embedding
            else:
                logger.error(
                    f"Triton inference failed: {response.status_code} - {response.text}"
                )
                return None
        except Exception as e:
            logger.error(f"Error calling Triton for embedding: {e}")
            return None

    def _embed_batch_with_triton(self, texts: List[str]) -> List[Optional[List[float]]]:
        try:
            payload = {
                "inputs": [
                    {
                        "name": "input_text",
                        "shape": [len(texts)],
                        "datatype": "BYTES",
                        "data": texts,
                    }
                ]
            }

            response = self.client.post(
                f"{self.triton_url}/v2/models/{self.model_name}/infer",
                json=payload,
            )

            if response.status_code == 200:
                result = response.json()
                embeddings = result["outputs"][0]["data"]
                # Assuming embeddings are returned as flattened array, reshape if needed
                embedding_dim = len(embeddings) // len(texts)
                return [
                    embeddings[i * embedding_dim : (i + 1) * embedding_dim]
                    for i in range(len(texts))
                ]
            else:
                logger.error(f"Triton batch inference failed: {response.status_code}")
                return [None] * len(texts)
        except Exception as e:
            logger.error(f"Error calling Triton for batch embedding: {e}")
            return [None] * len(texts)

    def _embed_with_openai(self, text: str) -> Optional[List[float]]:
        if not self.openai_client:
            return None

        try:
            fallback_model = get_embedding_fallback()
            response = self.openai_client.embeddings.create(
                model=fallback_model,
                input=text,
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
            response = self.client.get(f"{self.triton_url}/v2/health/ready")
            if response.status_code == 200:
                logger.info("Triton embedding service is healthy")
                return True
            else:
                logger.warning(f"Triton health check failed: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"Error checking Triton health: {e}")
            return False


_embedding_service_instance = None


def get_embedding_service() -> Qwen3EmbeddingService:
    global _embedding_service_instance
    if _embedding_service_instance is None:
        _embedding_service_instance = Qwen3EmbeddingService()
    return _embedding_service_instance
