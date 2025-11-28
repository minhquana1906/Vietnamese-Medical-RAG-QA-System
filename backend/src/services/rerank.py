from typing import Any, Dict, List, Optional, Tuple

import httpx
from loguru import logger

from ..configs.setup import get_backend_settings
from ..core.model_config import get_reranking_model

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

    DEFAULT_TASK_INSTRUCTION = (
        "Given a medical question in Vietnamese, retrieve relevant medical knowledge "
        "passages that provide accurate information to answer the question"
    )

    def __init__(
        self,
        local_url: Optional[str] = None,
        task_instruction: Optional[str] = None,
    ):
        """Initialize Qwen3 Reranker Service with local GPU service."""
        if settings.qwen3_models_enabled:
            self.local_url = local_url or settings.qwen3_models_url
        else:
            self.local_url = local_url or settings.backend_api_url

        self.huggingface_model = get_reranking_model()
        self.task_instruction = task_instruction or self.DEFAULT_TASK_INSTRUCTION
        self.client = httpx.Client(timeout=120.0)

    def rerank(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        top_n: int = 5,
        task_instruction: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], str]:
        """Rerank documents using Qwen3-Reranker-0.6B."""
        instruction = task_instruction or self.task_instruction

        try:
            reranked_results = self._rerank_with_local(
                query, documents, top_n, instruction
            )
            rerank_context = self._format_rerank_context(documents, reranked_results)
            return reranked_results, rerank_context
        except Exception as e:
            logger.error(f"[RERANK] Failed: {e}")
            # Return original order with neutral scores on failure
            fallback_results = [
                {"index": i, "relevance_score": 0.0, "document": doc}
                for i, doc in enumerate(documents[:top_n])
            ]
            rerank_context = self._format_rerank_context(documents, fallback_results)
            return fallback_results, rerank_context

    def _rerank_with_local(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        top_n: int,
        instruction: str,
    ) -> List[Dict[str, Any]]:
        """Call local GPU service for Qwen3-Reranker-0.6B inference."""
        doc_texts = [
            f"Title: {doc.get('title', '')}\nContent: {doc.get('content', '')}"
            for doc in documents
        ]

        payload = {
            "query": query,
            "documents": doc_texts,
            "top_n": top_n,
            "instruction": instruction,
        }

        response = self.client.post(
            f"{self.local_url}/v1/models/rerank",
            json=payload,
        )

        if response.status_code != 200:
            raise Exception(f"Reranking failed: {response.status_code}")

        result = response.json()
        scores = result["scores"]
        indices = result["indices"]

        scored_docs = [
            {
                "index": indices[i],
                "relevance_score": scores[i],
                "document": documents[indices[i]],
            }
            for i in range(len(indices))
        ]

        return scored_docs

    def _format_rerank_context(
        self, documents: List[Dict[str, Any]], reranked_results: List[Dict[str, Any]]
    ) -> str:
        """Format reranked documents into context string."""
        context_parts = []
        for rank, result in enumerate(reranked_results, start=1):
            doc = result.get("document") or documents[result["index"]]
            score = result["relevance_score"]
            context_parts.append(
                f"[Tài liệu {rank}] (Relevance: {score:.2f})\n"
                f"{doc.get('title', 'N/A')}\n"
                f"{doc.get('content', 'N/A')}"
            )
        return "\n\n---\n\n".join(context_parts)


_qwen3_reranker_instance = None


def get_qwen3_reranker() -> Qwen3RerankerService:
    global _qwen3_reranker_instance
    if _qwen3_reranker_instance is None:
        _qwen3_reranker_instance = Qwen3RerankerService()
    return _qwen3_reranker_instance
