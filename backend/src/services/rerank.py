from typing import Any, Dict, List, Optional, Tuple

import cohere
import httpx
import yaml
from loguru import logger

from ..configs.setup import get_backend_settings
from ..core.model_config import (
    get_reranking_model,
    get_reranking_fallback,
)

settings = get_backend_settings()


class Qwen3RerankerService:
    """
    Qwen3 Reranker Service following official Qwen3-Reranker-0.6B best practices.

    Key Features:
    - Format: <Instruct>: {instruction}\n<Query>: {query}\n<Document>: {doc}
    - System prompt: "Judge whether the Document meets the requirements..."
    - Output: "yes"/"no" tokens with logprobs for scoring
    - Instruction-aware: Custom instructions improve performance by 1-5%

    Reference: https://huggingface.co/Qwen/Qwen3-Reranker-0.6B
    """

    # Default task instruction for medical retrieval (recommended by Qwen team)
    DEFAULT_TASK_INSTRUCTION = (
        "Given a medical question, retrieve relevant medical knowledge passages "
        "that provide accurate information to answer the question"
    )

    def __init__(
        self,
        local_url: Optional[str] = None,
        cohere_fallback: bool = True,
        task_instruction: Optional[str] = None,
    ):
        """
        Initialize Qwen3 Reranker Service with local FastAPI backend.

        Args:
            local_url: Local backend URL (defaults to settings.backend_api_url)
            cohere_fallback: Enable Cohere fallback if local fails
            task_instruction: Custom task instruction (default: medical retrieval)
        """
        self.local_url = local_url or settings.backend_api_url
        self.huggingface_model = get_reranking_model()
        self.task_instruction = task_instruction or self.DEFAULT_TASK_INSTRUCTION

        logger.debug(
            f"Init Qwen3RerankerService: Local={self.local_url}, Model={self.huggingface_model}"
        )
        logger.debug(f"Task instruction: {self.task_instruction[:80]}...")

        self.cohere_fallback = cohere_fallback
        # Increase timeout for first-time model loading (30s -> 120s)
        self.client = httpx.Client(timeout=120.0)

    def rerank(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        top_n: int = 5,
        task_instruction: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], str]:
        """
        Rerank documents using Qwen3-Reranker-0.6B.

        Args:
            query: User query
            documents: List of document dicts (with 'title' and 'content' keys)
            top_n: Number of top results to return
            task_instruction: Override default task instruction

        Returns:
            Tuple of (reranked_results, formatted_context)
        """
        # Try local reranker first
        try:
            instruction = task_instruction or self.task_instruction
            reranked_results = self._rerank_with_local(
                query, documents, top_n, instruction
            )
            rerank_context = self._format_rerank_context(documents, reranked_results)
            logger.debug(
                f"✅ Reranked {len(reranked_results)} documents with Qwen3-Reranker"
            )
            return reranked_results, rerank_context
        except Exception as e:
            logger.warning(f"❌ Local Qwen3-Reranker failed: {e}")

        # Fallback to Cohere
        if self.cohere_fallback:
            logger.info("🔄 Fallback to Cohere reranking")
            return cohere_rerank(query, documents, top_n=top_n)

        # If no fallback, return original documents
        logger.warning(
            "⚠️ No reranking fallback available, returning original documents"
        )
        rerank_context = self._format_rerank_context(
            documents,
            [
                {"index": i, "relevance_score": 1.0}
                for i in range(min(top_n, len(documents)))
            ],
        )
        return documents[:top_n], rerank_context

    def _rerank_with_local(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        top_n: int,
        instruction: str,
    ) -> List[Dict[str, Any]]:
        """
        Call local FastAPI endpoint for Qwen3-Reranker-0.6B inference.

        Format follows Qwen3 specification:
        <Instruct>: {instruction}\n<Query>: {query}\n<Document>: {doc}
        """
        # Prepare document texts (Title + Content)
        doc_texts = [
            f"Title: {doc.get('title', '')}\nContent: {doc.get('content', '')}"
            for doc in documents
        ]

        # Local API request (backend will format with Qwen3 template)
        payload = {
            "query": query,
            "documents": doc_texts,
            "top_n": top_n,
            "instruction": instruction,  # Pass instruction to backend
        }

        response = self.client.post(
            f"{self.local_url}/v1/models/rerank",
            json=payload,
        )

        if response.status_code != 200:
            raise Exception(
                f"Local reranking failed: {response.status_code} - {response.text}"
            )

        result = response.json()
        scores = result["scores"]
        indices = result["indices"]

        # Create reranked results with dict format (consistent interface)
        scored_docs = [
            {
                "index": indices[i],
                "relevance_score": scores[i],
                "document": documents[indices[i]],  # Include original document
            }
            for i in range(len(indices))
        ]

        return scored_docs

    def _format_rerank_context(
        self, documents: List[Dict[str, Any]], reranked_results: List[Dict[str, Any]]
    ) -> str:
        """
        Format reranked documents into context string.

        Args:
            documents: Original document list (unused, kept for backward compatibility)
            reranked_results: List of dicts with keys: index, relevance_score, document

        Returns:
            Formatted context string with ranked documents
        """
        context_parts = []
        for rank, result in enumerate(reranked_results, start=1):
            # Use embedded document if available, otherwise fallback to documents list
            doc = result.get("document") or documents[result["index"]]
            score = result["relevance_score"]
            context_parts.append(
                f"#Rank {rank} (Relevance Score = {score:.3f}):\n"
                f"Title: {doc.get('title', 'N/A')}\n"
                f"Content: {doc.get('content', 'N/A')}"
            )
        return "\n\n".join(context_parts)


_qwen3_reranker_instance = None


def get_qwen3_reranker() -> Qwen3RerankerService:
    global _qwen3_reranker_instance
    if _qwen3_reranker_instance is None:
        _qwen3_reranker_instance = Qwen3RerankerService()
    return _qwen3_reranker_instance


def get_cohere_client():
    try:
        api_key = settings.cohere_api_key
        if not api_key:
            raise ValueError("COHERE_API_KEY environment variable not set.")
        client = cohere.Client(api_key)
        return client
    except Exception as e:
        logger.error(f"Error initializing Cohere client: {e}")
        raise


def cohere_rerank(
    query: str,
    relevant_docs: List[Dict[str, Any]],
    model: Optional[str] = None,
    top_n: int = 5,
) -> Tuple[List[Dict[str, Any]], str]:
    """
    Rerank documents using Cohere API.

    Returns normalized dict format consistent with Qwen3RerankerService:
    [{"index": int, "relevance_score": float, "document": dict}, ...]
    """
    try:
        # Use fallback model from config if not specified
        if model is None:
            model = get_reranking_fallback()

        client = get_cohere_client()
        yaml_docs = [yaml.dump(doc, sort_keys=False) for doc in relevant_docs]

        cohere_results = client.rerank(
            query=query, documents=yaml_docs, model=model, top_n=top_n
        ).results
        logger.debug(f"Reranked documents with Cohere model={model}: {cohere_results}")

        # Normalize Cohere response to dict format (consistent with Qwen3)
        reranked_documents = [
            {
                "index": result.index,
                "relevance_score": result.relevance_score,
                "document": relevant_docs[result.index],
            }
            for result in cohere_results
        ]

        rerank_context = "\n\n".join(
            [
                f"#Rank {rank} (Relevance Score = {doc['relevance_score']:.3f}):\n"
                f"Title: {doc['document']['title']}\n"
                f"Content: {doc['document']['content']}"
                for rank, doc in enumerate(reranked_documents, start=1)
            ]
        )
        logger.info(f"Reranked {len(reranked_documents)} docs with Cohere")

        return reranked_documents, rerank_context
    except Exception as e:
        logger.error(f"Error reranking documents with Cohere: {e}")
        raise
