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

    def __init__(
        self,
        local_url: str = "http://localhost:8000",
        cohere_fallback: bool = True,
    ):
        """
        Initialize Qwen3 Reranker Service with local FastAPI backend.

        Args:
            local_url: Local backend URL
            cohere_fallback: Enable Cohere fallback if local fails
        """
        self.local_url = local_url
        self.huggingface_model = get_reranking_model()

        logger.debug(
            f"Init Qwen3RerankerService: Local={local_url}, Model={self.huggingface_model}"
        )

        self.cohere_fallback = cohere_fallback
        self.client = httpx.Client(timeout=30.0)

    def rerank(
        self, query: str, documents: List[Dict[str, Any]], top_n: int = 5
    ) -> Tuple[List[Dict[str, Any]], str]:
        # Try local reranker first
        try:
            reranked_results = self._rerank_with_local(query, documents, top_n)
            rerank_context = self._format_rerank_context(documents, reranked_results)
            logger.debug(
                f"Reranked {len(reranked_results)} documents with local Qwen3-Reranker"
            )
            return reranked_results, rerank_context
        except Exception as e:
            logger.warning(f"Local Qwen3-Reranker failed: {e}")

        # Fallback to Cohere
        if self.cohere_fallback:
            logger.info("🔄 Fallback to Cohere reranking")
            return cohere_rerank(query, documents, top_n=top_n)

        # If no fallback, return original documents
        logger.warning("No reranking fallback available, returning original documents")
        rerank_context = self._format_rerank_context(
            documents,
            [
                {"index": i, "relevance_score": 1.0}
                for i in range(min(top_n, len(documents)))
            ],
        )
        return documents[:top_n], rerank_context

    def _rerank_with_local(
        self, query: str, documents: List[Dict[str, Any]], top_n: int
    ) -> List[Dict[str, Any]]:
        """Call local FastAPI endpoint"""
        # Prepare document texts
        doc_texts = [
            f"Title: {doc.get('title', '')}\nContent: {doc.get('content', '')}"
            for doc in documents
        ]

        # Local API request
        payload = {"query": query, "documents": doc_texts, "top_n": top_n}

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

        # Create reranked results
        scored_docs = [
            {"index": indices[i], "relevance_score": scores[i]}
            for i in range(len(indices))
        ]

        return scored_docs

    def _format_rerank_context(
        self, documents: List[Dict[str, Any]], reranked_results: List[Dict[str, Any]]
    ) -> str:
        """Format reranked documents into context string."""
        context_parts = []
        for rank, result in enumerate(reranked_results, start=1):
            doc = documents[result["index"]]
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
    """Rerank documents using Cohere API."""
    try:
        # Use fallback model from config if not specified
        if model is None:
            model = get_reranking_fallback()

        client = get_cohere_client()
        yaml_docs = [yaml.dump(doc, sort_keys=False) for doc in relevant_docs]

        reranked_documents = client.rerank(
            query=query, documents=yaml_docs, model=model, top_n=top_n
        ).results
        logger.debug(
            f"Reranked documents with Cohere model={model}: {reranked_documents}"
        )

        rerank_context = "\n\n".join(
            [
                f"#Rank {rank} (Relevance Score = {doc.relevance_score:.3f}):\nTitle: {relevant_docs[doc.index]['title']}\nContent: {relevant_docs[doc.index]['content']}"
                for rank, doc in enumerate(reranked_documents, start=1)
            ]
        )
        logger.info(f"Reranked {len(reranked_documents)} docs with Cohere")

        result = (reranked_documents, rerank_context)
        return result
    except Exception as e:
        logger.error(f"Error reranking documents with Cohere: {e}")
        raise
