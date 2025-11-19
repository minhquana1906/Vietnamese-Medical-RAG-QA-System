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
    IngestDatasetRequest,
    IngestDatasetResponse,
    IndexingJobStatusResponse,
    DocumentCreate,
    DocumentResponse,
    DocumentDetailResponse,
    DocumentListResponse,
    ReindexDocumentResponse,
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


# ============================================================================
# Document Management & Indexing Endpoints
# ============================================================================


@app.post("/indexing/ingest-dataset", response_model=IngestDatasetResponse)
async def ingest_dataset(request: IngestDatasetRequest):
    """
    Ingest a HuggingFace dataset by loading, chunking, and indexing to Qdrant + Elasticsearch.

    Returns a job ID for tracking progress via GET /indexing/jobs/{job_id}.
    """
    try:
        from .tasks import ingest_dataset_task

        # Start async Celery task
        task = ingest_dataset_task.delay(
            dataset_name=request.dataset_name,
            dataset_config=request.dataset_config,
            split=request.split,
            doc_type=request.doc_type,
            max_documents=request.max_documents,
        )

        logger.info(
            f"Dataset ingestion started: {request.dataset_name} (job_id: {task.id})"
        )

        return IngestDatasetResponse(
            job_id=task.id,
            status="pending",
            message="Dataset ingestion started",
        )

    except Exception as e:
        logger.error(f"Failed to start dataset ingestion: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/indexing/jobs/{job_id}", response_model=IndexingJobStatusResponse)
async def get_indexing_job_status(job_id: str):
    """
    Check the status of a background indexing job.

    Returns job status (pending, running, completed, failed) with progress information.
    """
    try:
        from celery.result import AsyncResult
        from .configs.celery_config import celery_app

        task_result = AsyncResult(job_id, app=celery_app)

        status = task_result.status.lower()

        response = IndexingJobStatusResponse(
            job_id=job_id,
            status=status,
            progress=None,
            result=None,
            error=None,
        )

        if status == "pending":
            response.status = "pending"
        elif status == "started" or status == "progress":
            response.status = "running"
            # Get progress info from task state
            if task_result.info and isinstance(task_result.info, dict):
                response.progress = task_result.info
        elif status == "success":
            response.status = "completed"
            response.result = task_result.result
        elif status == "failure":
            response.status = "failed"
            response.error = str(task_result.info)

        return response

    except Exception as e:
        logger.error(f"Failed to get job status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/documents", response_model=DocumentListResponse)
async def list_documents(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    source: Optional[str] = Query(None),
    doc_type: Optional[str] = Query(None),
    is_indexed: Optional[bool] = Query(None),
):
    """
    List all documents with pagination and filtering.
    """
    try:
        from sqlalchemy import func
        from .models import Document

        with SessionLocal() as db:
            # Build query
            query = db.query(Document)

            # Apply filters
            if source:
                query = query.filter(Document.metadata_["source"].astext == source)
            if doc_type:
                query = query.filter(Document.metadata_["doc_type"].astext == doc_type)
            if is_indexed is not None:
                query = query.filter(
                    Document.metadata_["is_indexed"].astext == str(is_indexed).lower()
                )

            # Get total count
            total = query.count()

            # Apply pagination
            documents = (
                query.order_by(Document.createdAt.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )

            # Convert to response
            doc_responses = []
            for doc in documents:
                metadata = doc.metadata_ or {}
                doc_responses.append(
                    DocumentResponse(
                        id=doc.id,
                        title=doc.title,
                        content=doc.content,
                        source=metadata.get("source"),
                        doc_type=metadata.get("doc_type"),
                        language=metadata.get("language", "vi"),
                        created_at=doc.createdAt.isoformat() if doc.createdAt else "",
                        is_indexed=metadata.get("is_indexed", False),
                        metadata=metadata,
                    )
                )

            return DocumentListResponse(
                documents=doc_responses,
                total=total,
                limit=limit,
                offset=offset,
            )

    except Exception as e:
        logger.error(f"Failed to list documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/documents", response_model=DocumentResponse, status_code=201)
async def create_document(request: DocumentCreate):
    """
    Manually create a document (not from HuggingFace dataset).

    Use POST /indexing/reindex-document/{document_id} to chunk and index this document.
    """
    try:
        from .models import Document

        with SessionLocal() as db:
            # Create document
            metadata = request.metadata or {}
            metadata.update(
                {
                    "source": request.source,
                    "doc_type": request.doc_type,
                    "language": request.language,
                    "is_indexed": False,
                }
            )

            new_doc = Document(
                title=request.title,
                content=request.content,
                metadata_=metadata,
            )

            db.add(new_doc)
            db.commit()
            db.refresh(new_doc)

            logger.info(f"Created document: {new_doc.title} (ID: {new_doc.id})")

            return DocumentResponse(
                id=new_doc.id,
                title=new_doc.title,
                content=new_doc.content,
                source=metadata.get("source"),
                doc_type=metadata.get("doc_type"),
                language=metadata.get("language", "vi"),
                created_at=new_doc.createdAt.isoformat(),
                is_indexed=False,
                metadata=metadata,
            )

    except Exception as e:
        logger.error(f"Failed to create document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/documents/{document_id}", response_model=DocumentDetailResponse)
async def get_document(document_id: UUID):
    """
    Get document details with all chunks.
    """
    try:
        from .models import Document, Chunk
        from .schemas.schema import ChunkResponse

        with SessionLocal() as db:
            doc = db.query(Document).filter(Document.id == document_id).first()

            if not doc:
                raise HTTPException(status_code=404, detail="Document not found")

            metadata = doc.metadata_ or {}

            # Get all chunks for this document
            chunks = (
                db.query(Chunk)
                .filter(Chunk.documentId == document_id)
                .order_by(Chunk.chunkIndex)
                .all()
            )

            chunk_responses = []
            for chunk in chunks:
                chunk_metadata = chunk.metadata_ or {}
                chunk_responses.append(
                    ChunkResponse(
                        id=chunk.id,
                        document_id=chunk.documentId,
                        chunk_index=chunk.chunkIndex,
                        content=chunk.content,
                        token_count=chunk_metadata.get("token_count"),
                        overlap_start=chunk_metadata.get("overlap_start"),
                        overlap_end=chunk_metadata.get("overlap_end"),
                        created_at=(
                            chunk.createdAt.isoformat() if chunk.createdAt else ""
                        ),
                        metadata=chunk_metadata,
                    )
                )

            return DocumentDetailResponse(
                id=doc.id,
                title=doc.title,
                content=doc.content,
                source=metadata.get("source"),
                doc_type=metadata.get("doc_type"),
                language=metadata.get("language", "vi"),
                created_at=doc.createdAt.isoformat() if doc.createdAt else "",
                is_indexed=metadata.get("is_indexed", False),
                metadata=metadata,
                chunks=chunk_responses,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/documents/{document_id}", status_code=204)
async def delete_document(document_id: UUID):
    """
    Delete document and all its chunks from PostgreSQL, Qdrant, and Elasticsearch.
    """
    try:
        from .models import Document, Chunk
        from .core.vectorize import qdrant_client, settings as vectorize_settings
        from .services.elasticsearch import es_client, settings as es_settings

        with SessionLocal() as db:
            doc = db.query(Document).filter(Document.id == document_id).first()

            if not doc:
                raise HTTPException(status_code=404, detail="Document not found")

            # Get all chunk IDs
            chunks = db.query(Chunk).filter(Chunk.documentId == document_id).all()
            chunk_ids = [str(chunk.id) for chunk in chunks]

            # Delete from Qdrant
            if chunk_ids:
                try:
                    qdrant_client.delete(
                        collection_name=vectorize_settings.qdrant_collection_name,
                        points_selector=chunk_ids,
                    )
                    logger.info(f"Deleted {len(chunk_ids)} chunks from Qdrant")
                except Exception as e:
                    logger.warning(f"Failed to delete from Qdrant: {e}")

            # Delete from Elasticsearch
            if chunk_ids:
                try:
                    for chunk_id in chunk_ids:
                        try:
                            es_client.delete(
                                index=es_settings.elasticsearch_index,
                                id=chunk_id,
                                ignore=[404],
                            )
                        except Exception as e:
                            logger.warning(
                                f"Failed to delete chunk {chunk_id} from Elasticsearch: {e}"
                            )
                    logger.info(f"Deleted {len(chunk_ids)} chunks from Elasticsearch")
                except Exception as e:
                    logger.warning(f"Failed to delete from Elasticsearch: {e}")

            # Delete from PostgreSQL (cascades to chunks)
            db.delete(doc)
            db.commit()

            logger.info(f"Deleted document {document_id} with {len(chunk_ids)} chunks")

            return None

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post(
    "/indexing/reindex-document/{document_id}", response_model=ReindexDocumentResponse
)
async def reindex_document(document_id: UUID):
    """
    Reindex a specific document by deleting existing chunks and re-chunking/re-indexing.

    Returns a job ID for tracking progress via GET /indexing/jobs/{job_id}.
    """
    try:
        from .models import Document
        from .tasks import reindex_document_task

        with SessionLocal() as db:
            doc = db.query(Document).filter(Document.id == document_id).first()

            if not doc:
                raise HTTPException(status_code=404, detail="Document not found")

        # Start async reindexing task
        task = reindex_document_task.delay(str(document_id))

        logger.info(f"Document reindexing started: {document_id} (job_id: {task.id})")

        return ReindexDocumentResponse(
            job_id=task.id,
            status="pending",
            message="Document reindexing started",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start reindexing: {e}")
        raise HTTPException(status_code=500, detail=str(e))
