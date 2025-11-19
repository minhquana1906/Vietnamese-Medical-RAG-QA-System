import time
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query
from loguru import logger
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import Counter, Histogram, make_asgi_app

from .configs.setup import get_backend_settings
from .core.vectorize import create_collection
from .core.model_loader import get_model_registry
from .database import SessionLocal
from .helpers import check_cache_health, check_database_health
from .models import init_db, insert_document
from .schemas.schema import (
    HealthCheckResponse,
    RAGQueryRequest,
    RAGQueryResponse,
    SystemHealthResponse,
    EmbedRequest,
    EmbedResponse,
    RerankRequest,
    RerankResponse,
    GuardRequest,
    GuardResponse,
)
from .services.rag_service import handle_rag_query
from .tasks import chunk_and_index_document

settings = get_backend_settings()

# RAG pipeline metrics
rag_requests_total = Counter(
    "rag_requests_total",
    "Total number of RAG requests",
    ["bot_id", "status"],
)

rag_request_duration_seconds = Histogram(
    "rag_request_duration_seconds",
    "RAG request processing duration in seconds",
    ["bot_id", "stage"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
)

# Cache metrics
cache_hits_total = Counter(
    "cache_hits_total",
    "Total number of cache hits",
    ["cache_type"],
)

cache_misses_total = Counter(
    "cache_misses_total",
    "Total number of cache misses",
    ["cache_type"],
)

# Search metrics
rag_search_requests_total = Counter(
    "rag_search_requests_total",
    "Total number of RAG search requests by type",
    ["search_type"],  # vector, keyword, hybrid
)

rag_search_duration_seconds = Histogram(
    "rag_search_duration_seconds",
    "Search duration by type in seconds",
    ["search_type"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
)

# Model inference metrics
model_inference_duration_seconds = Histogram(
    "model_inference_duration_seconds",
    "Model inference duration in seconds",
    ["model_type", "model_name"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0],
)

# Document indexing metrics
document_indexing_total = Counter(
    "document_indexing_total",
    "Total number of documents indexed",
    ["status"],
)

document_indexing_duration_seconds = Histogram(
    "document_indexing_duration_seconds",
    "Document indexing duration in seconds",
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
)

# Configure OpenTelemetry tracer
tracer_provider = TracerProvider()
trace.set_tracer_provider(tracer_provider)
tracer = trace.get_tracer(__name__)

# Configure OTLP exporter for Tempo
try:
    otlp_exporter = OTLPSpanExporter(
        endpoint=(
            settings.tempo_endpoint
            if hasattr(settings, "tempo_endpoint")
            else "http://tempo:4317"
        ),
        insecure=True,
    )
    span_processor = BatchSpanProcessor(otlp_exporter)
    tracer_provider.add_span_processor(span_processor)
    logger.info("OpenTelemetry tracing configured successfully")
except Exception as e:
    logger.warning(
        f"Failed to configure OpenTelemetry exporter: {e}. Tracing will be disabled."
    )

# FastAPI
app = FastAPI(title=settings.app_name, version=settings.app_version)

# Instrument FastAPI with OpenTelemetry
FastAPIInstrumentor.instrument_app(app)

# Mount Prometheus metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


@app.on_event("startup")
def on_startup():
    try:
        init_db()
        create_collection()

        # Load models for local inference
        try:
            model_registry = get_model_registry()
            model_registry.load_models()
            logger.info("✅ Models loaded successfully")
        except Exception as e:
            logger.warning(f"⚠️  Failed to load models (will use fallbacks): {e}")

        logger.info("Application startup complete.")
    except Exception as e:
        logger.error(f"Error during startup: {e}")
        raise


@app.get("/")
def read_root():
    return {"message": f"Welcome to the {settings.app_name} API!"}


@app.get("/v1/ready")
async def readiness_check():
    try:
        return {"status": "ready", "timestamp": time.time()}
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        raise HTTPException(status_code=503, detail="Service not ready")


@app.get("/v1/health", response_model=SystemHealthResponse)
async def health_check():
    with tracer.start_as_current_span("health_check"):
        # Check API
        api_health = HealthCheckResponse(
            status="ok", service="api", details={"version": settings.app_version}
        )

        # Check Database
        db_health = await check_database_health()

        # Check Cache (Redis)
        cache_health = await check_cache_health()

        # Determine overall system status
        statuses = [api_health.status, db_health.status, cache_health.status]
        if all(s == "ok" for s in statuses):
            overall_status = "healthy"
        elif any(s == "error" for s in statuses):
            overall_status = "unhealthy"
        else:
            overall_status = "degraded"

        return SystemHealthResponse(
            status=overall_status,
            api=api_health,
            database=db_health,
            cache=cache_health,
        )


# Qdrant endpoints
@app.post("/v1/collections/create")
def create_collection_endpoint(
    collection_name: str = settings.default_collection_name,
    vector_size: int = settings.vector_dimension,
):
    try:
        status = create_collection(collection_name, vector_size)
        return {"status": status}
    except Exception as e:
        logger.error(f"Error creating collection via endpoint: {e}")
        raise HTTPException(status_code=500, detail="Internal server error.")


@app.post("/v1/documents/create")
def insert_document_endpoint(title: str, content: str):
    with tracer.start_as_current_span("insert_document") as span:
        span.set_attribute("document.title", title)
        start_time = time.time()
        try:
            new_docs = insert_document(title, content)
            doc_id = str(new_docs.id)
            chunk_and_index_document.delay(doc_id, title, content)
            document_indexing_total.labels(status="queued").inc()
            duration = time.time() - start_time
            document_indexing_duration_seconds.observe(duration)
            return {
                "status": "Document received and indexing started.",
                "document_id": doc_id,
            }
        except Exception as e:
            logger.error(f"Error inserting document via endpoint: {e}")
            document_indexing_total.labels(status="error").inc()
            span.set_attribute("error", True)
            span.set_attribute("error.message", str(e))
            raise HTTPException(status_code=500, detail="Internal server error.")


# ============= Model Inference Endpoints =============


@app.post("/v1/models/rag", response_model=RAGQueryResponse)
async def rag_query(request: RAGQueryRequest):
    logger.info(
        f"RAG query from user={request.user_identifier}, thread={request.thread_id}"
    )

    with tracer.start_as_current_span("rag_query") as span:
        span.set_attribute("user_identifier", request.user_identifier)
        span.set_attribute("thread_id", request.thread_id)

        start_time = time.time()
        try:
            with SessionLocal() as db:
                response, sources = handle_rag_query(
                    db, request.user_identifier, request.thread_id, request.query
                )

            duration = time.time() - start_time
            rag_request_duration_seconds.labels(
                bot_id="meddy", stage="complete"
            ).observe(duration)
            rag_requests_total.labels(bot_id="meddy", status="success").inc()

            logger.info(f"RAG query completed in {duration:.2f}s")

            return RAGQueryResponse(
                thread_id=request.thread_id,
                response=response,
                sources=sources,
                metadata={"duration_seconds": duration},
            )

        except Exception as e:
            logger.error(f"Error processing RAG query: {e}")
            rag_requests_total.labels(bot_id="meddy", status="error").inc()
            span.set_attribute("error", True)
            span.set_attribute("error.message", str(e))
            raise HTTPException(
                status_code=500, detail=f"Error processing query: {str(e)}"
            )


@app.post("/v1/models/embed", response_model=EmbedResponse)
async def embed_endpoint(request: EmbedRequest):
    """Generate Qwen3 embeddings with instruction-awareness"""
    try:
        model_registry = get_model_registry()

        if not model_registry.is_ready():
            raise HTTPException(status_code=503, detail="Models not loaded")

        start_time = time.time()

        # Pass instruction parameters to Qwen3-Embedding
        embeddings = model_registry.embed_texts(
            texts=request.texts,
            normalize=request.normalize,
            is_query=request.is_query,
            instruction=request.instruction
            or "Given a medical query, retrieve relevant passages that answer the query",
        )

        duration = time.time() - start_time

        model_inference_duration_seconds.labels(
            model_type="embedding", model_name="qwen3"
        ).observe(duration)

        logger.debug(
            f"Embedded {len(embeddings)} texts (is_query={request.is_query}) in {duration:.3f}s"
        )

        from .core.model_config import get_embedding_model

        return EmbedResponse(embeddings=embeddings, model=get_embedding_model())

    except Exception as e:
        logger.error(f"Embedding error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/models/rerank", response_model=RerankResponse)
async def rerank_endpoint(request: RerankRequest):
    """Rerank documents using Qwen3-Reranker with task instruction"""
    try:
        model_registry = get_model_registry()

        if not model_registry.is_ready():
            raise HTTPException(status_code=503, detail="Models not loaded")

        start_time = time.time()

        # Pass instruction to Qwen3-Reranker
        scores, indices = model_registry.rerank_documents(
            query=request.query,
            documents=request.documents,
            top_n=request.top_n,
            instruction=request.instruction
            or "Given a medical query, determine if the passage contains the answer",
        )

        duration = time.time() - start_time

        model_inference_duration_seconds.labels(
            model_type="reranking", model_name="qwen3"
        ).observe(duration)

        logger.debug(f"Reranked {len(request.documents)} docs in {duration:.3f}s")

        from .core.model_config import get_reranking_model

        return RerankResponse(
            scores=scores, indices=indices, model=get_reranking_model()
        )

    except Exception as e:
        logger.error(f"Reranking error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/models/guard", response_model=GuardResponse)
async def guard_endpoint(request: GuardRequest):
    """Check content safety using Qwen3Guard with 3-tier severity"""
    try:
        model_registry = get_model_registry()

        if not model_registry.is_ready():
            raise HTTPException(status_code=503, detail="Models not loaded")

        start_time = time.time()

        # Qwen3Guard returns: (is_safe, severity, categories, is_refusal, raw_output)
        is_safe, severity, categories, is_refusal, raw_output = (
            model_registry.check_safety(
                text=request.text,
                check_type=request.check_type,
            )
        )

        duration = time.time() - start_time

        model_inference_duration_seconds.labels(
            model_type="guardrails", model_name="qwen3"
        ).observe(duration)

        logger.debug(
            f"Guard check in {duration:.3f}s: severity={severity}, categories={categories}, refusal={is_refusal}"
        )

        from .core.model_config import get_guardrails_model

        return GuardResponse(
            is_safe=is_safe,
            severity=severity,
            categories=categories,
            is_refusal=is_refusal,
            raw_output=raw_output,
            model=get_guardrails_model(),
        )

    except Exception as e:
        logger.error(f"Guardrails error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
