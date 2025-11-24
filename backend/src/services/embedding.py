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
    """
    Qwen3 Embedding Service following official Qwen3-Embedding-0.6B best practices.

    Key Features:
    - Instruction-aware: Queries require task instruction prefix
    - Documents: No instruction prefix needed
    - Normalization: Always normalize embeddings (L2 norm)
    - Model: Qwen/Qwen3-Embedding-0.6B (1024-dim)

    Reference: https://huggingface.co/Qwen/Qwen3-Embedding-0.6B
    """

    # Default task instruction for medical retrieval (recommended by Qwen team)
    DEFAULT_TASK_INSTRUCTION = (
        "Given a medical question, retrieve relevant medical knowledge passages "
        "that provide accurate information to answer the question"
    )

    def __init__(
        self,
        local_url: Optional[str] = None,
        openai_fallback: bool = True,
        task_instruction: Optional[str] = None,
    ):
        """
        Initialize Qwen3 Embedding Service with local FastAPI backend.

        Args:
            local_url: Local backend URL (defaults to settings.backend_api_url)
            openai_fallback: Enable OpenAI fallback if local fails
            task_instruction: Custom task instruction (default: medical retrieval)
        """
        # Auto-detect GPU service if enabled (prioritize GPU for performance)
        if settings.qwen3_models_enabled:
            self.local_url = local_url or settings.qwen3_models_url
            logger.info(f"Using Qwen3 GPU service: {self.local_url}")
        else:
            self.local_url = local_url or settings.backend_api_url
            logger.info(f"Using local CPU service: {self.local_url}")
        self.huggingface_model = get_embedding_model()
        self.task_instruction = task_instruction or self.DEFAULT_TASK_INSTRUCTION

        logger.debug(
            f"Init Qwen3EmbeddingService: Local={self.local_url}, Model={self.huggingface_model}"
        )
        logger.debug(f"Task instruction: {self.task_instruction[:80]}...")

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

    def embed_query(
        self, query: str, use_cache: bool = True, task_instruction: Optional[str] = None
    ) -> Optional[List[float]]:
        """
        Embed a query with instruction prefix (Qwen3 best practice).

        Args:
            query: User query text
            use_cache: Enable Redis caching
            task_instruction: Override default task instruction

        Returns:
            Normalized embedding vector (1024-dim)
        """
        instruction = task_instruction or self.task_instruction

        # Cache key includes instruction for accuracy
        cache_key = f"query:{instruction}:{query}"

        # Check cache first
        if use_cache:
            from ..core.cache import get_query_embedding

            cached_embedding = get_query_embedding(cache_key)
            if cached_embedding:
                logger.debug(f"Cache hit for query: {query[:50]}...")
                return cached_embedding

        # Try local inference (backend will format with instruction)
        embedding = self._embed_with_local(
            texts=[query], is_query=True, instruction=instruction
        )
        if embedding:
            embedding = embedding[0]

        # Fallback to OpenAI if local fails
        if embedding is None and self.openai_fallback:
            logger.warning("Local embedding failed, falling back to OpenAI")
            embedding = self._embed_with_openai(query)

        # Cache result if successful
        if embedding and use_cache:
            from ..core.cache import cache_query_embedding

            cache_query_embedding(cache_key, embedding)

        return embedding

    def embed_document(self, document: str) -> Optional[List[float]]:
        """
        Embed a document WITHOUT instruction prefix (Qwen3 best practice).

        Args:
            document: Document text

        Returns:
            Normalized embedding vector (1024-dim)
        """
        # Documents don't need instruction prefix (Qwen3 guideline)
        embedding = self._embed_with_local(
            texts=[document], is_query=False, instruction=None
        )
        if embedding:
            return embedding[0]

        # Fallback to OpenAI if local fails
        if self.openai_fallback:
            logger.warning("Local embedding failed, falling back to OpenAI")
            return self._embed_with_openai(document)

        return None

    def embed_text(self, text: str, use_cache: bool = True) -> Optional[List[float]]:
        """
        Legacy method for backward compatibility.
        Treats text as query (with instruction prefix).
        """
        return self.embed_query(text, use_cache=use_cache)

    def embed_batch_documents(
        self, documents: List[str], batch_size: int = 32
    ) -> List[Optional[List[float]]]:
        """
        Embed multiple documents WITHOUT instruction prefix (for indexing).

        Args:
            documents: List of document texts
            batch_size: Batch size for processing

        Returns:
            List of normalized embedding vectors
        """
        embeddings = []

        # Process in batches
        for i in range(0, len(documents), batch_size):
            batch = documents[i : i + batch_size]
            batch_embeddings = self._embed_with_local(
                texts=batch, is_query=False, instruction=None
            )

            # Fallback for failed embeddings
            if batch_embeddings is None and self.openai_fallback:
                logger.warning(f"Local failed for batch {i}, using OpenAI fallback")
                batch_embeddings = [self._embed_with_openai(doc) for doc in batch]

            embeddings.extend(batch_embeddings or [None] * len(batch))

        logger.debug(
            f"Generated {len(documents)} document embeddings (batch size: {batch_size})"
        )
        return embeddings

    def _embed_with_local(
        self,
        texts: List[str],
        is_query: bool = False,
        instruction: Optional[str] = None,
    ) -> Optional[List[List[float]]]:
        """
        Call local FastAPI endpoint for Qwen3-Embedding-0.6B inference.

        Args:
            texts: Raw texts to embed (NOT pre-formatted)
            is_query: If True, backend will add instruction prefix
            instruction: Task instruction (only used if is_query=True)

        Returns:
            List of normalized embedding vectors
        """
        try:
            # Qwen3 requires normalization (L2 norm)
            payload = {
                "texts": texts,
                "normalize": True,
                "is_query": is_query,
            }

            # Add instruction only if query
            if is_query and instruction:
                payload["instruction"] = instruction

            response = self.client.post(
                f"{self.local_url}/v1/models/embed",
                json=payload,
            )

            if response.status_code == 200:
                result = response.json()
                embeddings: List[List[float]] = result["embeddings"]
                logger.debug(
                    f"✅ Qwen3-Embedding generated {len(texts)} embeddings "
                    f"(is_query={is_query})"
                )
                return embeddings
            else:
                logger.error(
                    f"❌ Local embedding failed: {response.status_code} - {response.text}"
                )
                return None
        except Exception as e:
            logger.error(f"❌ Error calling local embedding: {e}")
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
