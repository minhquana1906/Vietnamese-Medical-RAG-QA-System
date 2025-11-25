"""Model Inference Endpoints (Embedding, Reranking, Guardrails)"""

import time
from typing import List

from fastapi import APIRouter, HTTPException
from loguru import logger

from ..configs.setup import get_backend_settings
from ..schemas.schema import (
    EmbedRequest,
    EmbedResponse,
    RerankRequest,
    RerankResponse,
    GuardRequest,
    GuardResponse,
)
from ..services.embedding import Qwen3EmbeddingService
from ..services.rerank import Qwen3RerankerService
from ..core.guardrails import Qwen3GuardService

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
        embeddings = await embedding_service.embed_batch_documents(
            texts=request.texts,
            normalize=request.normalize,
            is_query=request.is_query,
            instruction=request.instruction,
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
        results = await reranker_service.rerank(
            query=request.query,
            documents=request.documents,
            top_n=request.top_n,
            instruction=request.instruction,
        )

        duration = time.time() - start_time
        model_inference_duration_seconds.labels(
            model_type="reranker", model_name="qwen3-reranker"
        ).observe(duration)

        logger.info(
            f"Reranked {len(request.documents)} documents → top {request.top_n} in {duration:.3f}s"
        )

        return RerankResponse(
            scores=results["scores"],
            indices=results["indices"],
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
            result = await guardrails_service.validate_query(text=request.text)
        elif request.check_type == "output":
            if not request.query:
                raise HTTPException(
                    status_code=400,
                    detail="query is required for output safety check",
                )
            result = await guardrails_service.validate_response(
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
            f"Guardrails check ({request.check_type}): is_safe={result['is_safe']}, "
            f"severity={result['severity']}, duration={duration:.3f}s"
        )

        return GuardResponse(
            is_safe=result["is_safe"],
            severity=result["severity"],
            categories=result["categories"],
            is_refusal=result.get("is_refusal", False),
            raw_output=result.get("raw_output", ""),
            model="Qwen/Qwen3Guard-Gen-0.6B",
            usage={"duration_seconds": duration},
        )

    except Exception as e:
        logger.error(f"Guardrails check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
