import asyncio
import time

from celery.result import AsyncResult
from fastapi import FastAPI, HTTPException
from loguru import logger
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import \
    OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import Counter, Histogram, make_asgi_app

from .configs.setup import get_backend_settings
from .core.vectorize import create_collection
from .helpers import check_cache_health, check_database_health
from .models import init_db, insert_document
from .schemas.chainlit_schema import HealthCheckResponse, SystemHealthResponse
from .schemas.schema import CompleteRequest
from .tasks import chunk_and_index_document, message_handler_task

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
        logger.info("Application startup complete.")
    except Exception as e:
        logger.error(f"Error during startup: {e}")
        raise


@app.get("/")
def read_root():
    return {"message": f"Welcome to the {settings.app_name} API!"}


@app.get("/ready")
async def readiness_check():
    try:
        return {"status": "ready", "timestamp": time.time()}
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        raise HTTPException(status_code=503, detail="Service not ready")


# Task endpoints
@app.post("/chat/complete")
async def chat_complete(request: CompleteRequest):
    bot_id = request.bot_id
    user_id = request.user_id
    user_message = request.user_message
    is_sync_request = request.is_sync_request

    if not bot_id or not user_id or not user_message:
        raise HTTPException(status_code=400, detail="Missing required fields")

    logger.info(f"Chat request from user {user_id} to bot {bot_id}: {user_message}")

    # Start tracing span
    with tracer.start_as_current_span("chat_complete") as span:
        span.set_attribute("bot_id", bot_id)
        span.set_attribute("user_id", user_id)
        span.set_attribute("is_sync", is_sync_request or False)

        start_time = time.time()
        try:
            if is_sync_request:
                response = message_handler_task(bot_id, user_id, user_message)
                duration = time.time() - start_time
                rag_request_duration_seconds.labels(
                    bot_id=bot_id, stage="complete"
                ).observe(duration)
                rag_requests_total.labels(bot_id=bot_id, status="success").inc()
                return {"status": "completed", "response": response}
            else:
                response = message_handler_task.delay(bot_id, user_id, user_message)
                rag_requests_total.labels(bot_id=bot_id, status="queued").inc()
                return {"status": "processing", "task_id": response.id}
        except Exception as e:
            logger.error(f"Error processing chat request: {e}")
            rag_requests_total.labels(bot_id=bot_id, status="error").inc()
            span.set_attribute("error", True)
            span.set_attribute("error.message", str(e))
            raise HTTPException(status_code=500, detail="Internal server error.")


@app.get("/chat/complete/{task_id}")
async def get_chat_response(task_id: str):
    start = time.time()
    try:
        while True:
            task_result = AsyncResult(task_id)
            task_status = task_result.status
            if task_status == "PENDING" or task_status == "STARTED":
                if time.time() - start > 60:
                    return {
                        "task_id": task_id,
                        "status": task_result.status,
                        "task_result": task_result.result,
                        "error_message": "408 Request Timeout: The task is still pending after 60 seconds.",
                    }
                else:
                    # Wait 0.5s before checking again
                    await asyncio.sleep(0.5)
            else:
                return {
                    "task_id": task_id,
                    "status": task_result.status,
                    "task_result": task_result.result,
                }
    except Exception as e:
        logger.error(f"Error retrieving task {task_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error.")


# Qdrant endpoints
@app.post("/collections/create")
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


@app.post("/documents/create")
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


# ============= HEALTH CHECK ENDPOINTS =============


@app.get("/health", response_model=SystemHealthResponse)
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


@app.get("/health/db", response_model=HealthCheckResponse)
async def health_check_database():
    return await check_database_health()


@app.get("/health/cache", response_model=HealthCheckResponse)
async def health_check_cache():
    return await check_cache_health()
