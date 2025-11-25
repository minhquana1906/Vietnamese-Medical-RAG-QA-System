"""
Prometheus Metrics Definitions

Centralized metrics to avoid circular imports between main.py and routers.
"""

from prometheus_client import Counter, Histogram, Gauge, Info

# ============================================================================
# FASTAPI STANDARD METRICS (for dashboard compatibility)
# ============================================================================

# Application info (using Gauge instead of Info to avoid _info suffix)
fastapi_app_info = Gauge(
    "fastapi_app_info",
    "FastAPI application information",
    ["app_name", "version"],
)

# Request metrics
fastapi_requests_total = Counter(
    "fastapi_requests_total",
    "Total number of requests by method, path, and status",
    ["method", "path", "status_code", "app_name"],
)

fastapi_responses_total = Counter(
    "fastapi_responses_total",
    "Total number of responses by method, path, and status",
    ["method", "path", "status_code", "app_name"],
)

fastapi_requests_duration_seconds = Histogram(
    "fastapi_requests_duration_seconds",
    "Request duration in seconds",
    ["method", "path", "app_name"],
    buckets=[0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0],
)

fastapi_requests_in_progress = Gauge(
    "fastapi_requests_in_progress",
    "Number of requests currently in progress",
    ["method", "path", "app_name"],
)

fastapi_exceptions_total = Counter(
    "fastapi_exceptions_total",
    "Total number of exceptions raised",
    ["method", "path", "exception_type", "app_name"],
)

# Request/Response size metrics
fastapi_request_size_bytes = Histogram(
    "fastapi_request_size_bytes",
    "Request content length in bytes",
    ["method", "path", "app_name"],
    buckets=[100, 1000, 10000, 100000, 1000000],
)

fastapi_response_size_bytes = Histogram(
    "fastapi_response_size_bytes",
    "Response content length in bytes",
    ["method", "path", "app_name"],
    buckets=[100, 1000, 10000, 100000, 1000000],
)

# ============================================================================
# RAG PIPELINE METRICS (custom)
# ============================================================================

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

# Voice processing metrics
voice_request_duration_seconds = Histogram(
    "voice_request_duration_seconds",
    "Voice endpoint latency (end-to-end)",
    ["endpoint"],  # stt, tts, audio_rag
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0],
)

audio_rag_stage_duration_seconds = Histogram(
    "audio_rag_stage_duration_seconds",
    "Audio RAG pipeline stage latency",
    ["stage"],  # stt, rag, tts
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 20.0],
)

voice_request_errors_total = Counter(
    "voice_request_errors_total",
    "Voice request errors",
    ["endpoint", "error_type"],
)
