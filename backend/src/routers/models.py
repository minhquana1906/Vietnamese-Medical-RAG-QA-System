"""Model Inference Endpoints (Embedding, Reranking, Guardrails)"""

import time
from typing import List

from fastapi import APIRouter, HTTPException
from loguru import logger

from ..configs.setup import get_backend_settings
from ..core.guardrails import Qwen3GuardService
from ..schemas.schema import (
    EmbedRequest,
    EmbedResponse,
    GuardRequest,
    GuardResponse,
    RerankRequest,
    RerankResponse,
)
from ..services.embedding import Qwen3EmbeddingService
from ..services.rerank import Qwen3RerankerService

router = APIRouter(prefix="/v1/models", tags=["Model Inference"])

settings = get_backend_settings()

# Import metrics from centralized module
from ..core.metrics import model_inference_duration_seconds


@router.post("/embed", response_model=EmbedResponse)
async def embed_endpoint(request: EmbedRequest):
    """
    Generate Qwen3 embeddings with instruction-awareness

    Routes to GPU service for optimal performance

    Args:
        request: Texts to embed with optional instruction

    Returns:
        EmbedResponse: Vector embeddings
    """
    try:
        start_time = time.time()

        # Delegate to embedding service (auto-routes to GPU or CPU)
        embedding_service = Qwen3EmbeddingService()

        # Use the correct method based on query type
        if request.is_query:
            # For queries, use embed_query for each text
            embeddings = []
            for text in request.texts:
                emb = embedding_service.embed_query(
                    query=text, use_cache=False, task_instruction=request.instruction
                )
                embeddings.append(emb if emb else [])
        else:
            # For documents, use embed_batch_documents
            embeddings = embedding_service.embed_batch_documents(
                documents=request.texts, batch_size=32
            )

        duration = time.time() - start_time
        model_inference_duration_seconds.labels(
            model_type="embedding", model_name="qwen3-embedding"
        ).observe(duration)

        logger.info(
            f"Generated {len(embeddings)} embeddings in {duration:.3f}s "
            f"(is_query={request.is_query}, normalize={request.normalize})"
        )

        return EmbedResponse(
            embeddings=embeddings,
            model="Qwen/Qwen3-Embedding-0.6B",
            dimension=len(embeddings[0]) if embeddings else 0,
            usage={
                "total_texts": len(request.texts),
                "duration_seconds": duration,
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Embedding failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rerank", response_model=RerankResponse)
async def rerank_endpoint(request: RerankRequest):
    """
    Rerank documents using Qwen3-Reranker

    Routes to GPU service for optimal performance

    Args:
        request: Query and documents to rerank

    Returns:
        RerankResponse: Reranked documents with scores
    """
    try:
        start_time = time.time()

        # Delegate to reranker service (auto-routes to GPU or CPU)
        reranker_service = Qwen3RerankerService()

        # Convert string documents to dicts as expected by service
        doc_dicts = [{"content": d} for d in request.documents]

        results, _ = reranker_service.rerank(
            query=request.query,
            documents=doc_dicts,
            top_n=request.top_n,
            task_instruction=request.instruction,
        )

        duration = time.time() - start_time
        model_inference_duration_seconds.labels(
            model_type="reranker", model_name="qwen3-reranker"
        ).observe(duration)

        logger.info(
            f"Reranked {len(request.documents)} documents → top {request.top_n} in {duration:.3f}s"
        )

        # Extract scores and indices from results
        # results is a list of dicts: {'index': i, 'relevance_score': s, 'document': d}
        scores = [r["relevance_score"] for r in results]
        indices = [r["index"] for r in results]

        return RerankResponse(
            scores=scores,
            indices=indices,
            model="Qwen/Qwen3-Reranker-0.6B",
            usage={
                "total_documents": len(request.documents),
                "top_n": request.top_n,
                "duration_seconds": duration,
            },
        )

    except Exception as e:
        logger.error(f"Reranking failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/guard", response_model=GuardResponse)
async def guard_endpoint(request: GuardRequest):
    """
    Check content safety using Qwen3Guard

    Routes to GPU service for optimal performance

    Args:
        request: Text to check for safety

    Returns:
        GuardResponse: Safety assessment with categories
    """
    try:
        start_time = time.time()

        # Delegate to guardrails service (auto-routes to GPU or CPU)
        guardrails_service = Qwen3GuardService()

        if request.check_type == "input":
            is_safe, violation, metadata = guardrails_service.validate_query(
                query=request.text
            )
        elif request.check_type == "output":
            if not request.query:
                raise HTTPException(
                    status_code=400,
                    detail="query is required for output safety check",
                )
            is_safe, violation, metadata = guardrails_service.validate_response(
                query=request.query, response=request.text
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid check_type: {request.check_type}. Must be 'input' or 'output'",
            )

        duration = time.time() - start_time
        model_inference_duration_seconds.labels(
            model_type="guardrails", model_name="qwen3-guard"
        ).observe(duration)

        logger.info(
            f"Guardrails check ({request.check_type}): is_safe={is_safe}, "
            f"severity={metadata.get('severity')}, duration={duration:.3f}s"
        )

        return GuardResponse(
            is_safe=is_safe,
            severity=metadata.get("severity", "Unknown"),
            categories=metadata.get("categories", []),
            is_refusal=metadata.get("details", {}).get("is_refusal", False),
            raw_output=metadata.get("details", {}).get("raw_output", ""),
            model="Qwen/Qwen3Guard-Gen-0.6B",
            usage={"duration_seconds": duration},
        )

    except Exception as e:
        logger.error(f"Guardrails check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
