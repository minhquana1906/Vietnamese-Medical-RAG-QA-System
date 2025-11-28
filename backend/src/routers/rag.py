"""RAG Query Endpoints"""

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from opentelemetry import trace
from sqlalchemy.orm import Session

from ..core.metrics import rag_request_duration_seconds, rag_requests_total
from ..database import get_db_session
from ..schemas.schema import RAGQueryRequest, RAGQueryResponse
from ..services.rag_service import handle_rag_query

router = APIRouter(prefix="/v1/rag", tags=["RAG"])

# Get tracer
tracer = trace.get_tracer(__name__)


@router.post("", response_model=RAGQueryResponse)
def rag_query(request: RAGQueryRequest, db: Session = Depends(get_db_session)):
    """
    RAG Query Endpoint

    Pipeline: Query → Retrieval → Reranking → Generation → Response

    Args:
        request: RAG query with user_identifier, thread_id, query
        db: Database session (injected)

    Returns:
        RAGQueryResponse: Generated answer with source documents
    """
    logger.info(
        f"RAG query from user={request.user_identifier}, thread={request.thread_id}"
    )

    with tracer.start_as_current_span("rag_query") as span:
        span.set_attribute("user_identifier", request.user_identifier)
        span.set_attribute("thread_id", request.thread_id)
        span.set_attribute("query", request.query)

        try:
            # Call RAG service with correct signature
            response_text, sources = handle_rag_query(
                db=db,
                user_identifier=request.user_identifier,
                thread_id=request.thread_id,
                query=request.query,
            )

            # Build response object
            response = RAGQueryResponse(
                thread_id=request.thread_id,
                response=response_text,
                sources=sources,
                metadata=request.metadata,
            )

            # Metrics
            rag_requests_total.labels(
                bot_id=request.user_identifier, status="success"
            ).inc()

            return response

        except Exception as e:
            rag_requests_total.labels(
                bot_id=request.user_identifier, status="error"
            ).inc()
            logger.error(f"RAG query failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))
