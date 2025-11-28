from fastapi import FastAPI, Request, Response
from loguru import logger
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import make_asgi_app
import time

from .configs.setup import get_backend_settings
from .core.vectorize import create_collection
from .models import init_db

# Import metrics first (before routers to avoid circular import)
from .core import metrics  # noqa: F401

# Import routers
from .routers import health, rag, models, audio, documents

settings = get_backend_settings()

# Configure OpenTelemetry tracer
tracer_provider = TracerProvider()
trace.set_tracer_provider(tracer_provider)
tracer = trace.get_tracer(__name__)

# Configure OTLP exporter for Tempo
if settings.tempo_enabled:
    try:
        otlp_exporter = OTLPSpanExporter(
            endpoint=settings.tempo_endpoint,
            insecure=True,
        )
        span_processor = BatchSpanProcessor(otlp_exporter)
        tracer_provider.add_span_processor(span_processor)
        logger.info(f"✅ OpenTelemetry tracing configured: {settings.tempo_endpoint}")
    except Exception as e:
        logger.warning(
            f"⚠️  Failed to configure OpenTelemetry exporter: {e}. Tracing will be disabled."
        )
else:
    logger.info("⏭️  Tempo tracing disabled (TEMPO_ENABLED=false)")

# FastAPI
app = FastAPI(title=settings.app_name, version=settings.app_version)

# Instrument FastAPI with OpenTelemetry
FastAPIInstrumentor.instrument_app(app)

# Set app info metric (Gauge with labels)
from .core.metrics import fastapi_app_info

fastapi_app_info.labels(app_name=settings.app_name, version=settings.app_version).set(1)


# Add custom middleware for FastAPI metrics
@app.middleware("http")
async def prometheus_middleware(request: Request, call_next):
    """Custom middleware to track FastAPI metrics"""
    from .core.metrics import (
        fastapi_requests_total,
        fastapi_responses_total,
        fastapi_requests_duration_seconds,
        fastapi_requests_in_progress,
        fastapi_exceptions_total,
        fastapi_request_size_bytes,
        fastapi_response_size_bytes,
    )

    method = request.method
    path = request.url.path
    app_name = settings.app_name

    # Track in-progress requests
    fastapi_requests_in_progress.labels(
        method=method, path=path, app_name=app_name
    ).inc()

    # Track request size
    content_length = request.headers.get("content-length")
    if content_length:
        fastapi_request_size_bytes.labels(
            method=method, path=path, app_name=app_name
        ).observe(int(content_length))

    start_time = time.time()
    status_code = 500  # Default to 500 for errors
    response = None

    try:
        response = await call_next(request)
        status_code = response.status_code

        # Track response
        fastapi_responses_total.labels(
            method=method,
            path=path,
            status_code=f"{status_code // 100}xx",
            app_name=app_name,
        ).inc()

        # Track response size (get from headers if available)
        content_length = response.headers.get("content-length")
        if content_length:
            fastapi_response_size_bytes.labels(
                method=method, path=path, app_name=app_name
            ).observe(int(content_length))

        return response

    except Exception as e:
        # Track exception
        fastapi_exceptions_total.labels(
            method=method, path=path, exception_type=type(e).__name__, app_name=app_name
        ).inc()
        status_code = 500
        raise

    finally:
        # Track duration
        duration = time.time() - start_time
        fastapi_requests_duration_seconds.labels(
            method=method, path=path, app_name=app_name
        ).observe(duration)

        # Track total requests
        fastapi_requests_total.labels(
            method=method,
            path=path,
            status_code=f"{status_code // 100}xx",
            app_name=app_name,
        ).inc()

        # Decrement in-progress
        fastapi_requests_in_progress.labels(
            method=method, path=path, app_name=app_name
        ).dec()


# Mount Prometheus metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


@app.on_event("startup")
def on_startup():
    try:
        init_db()
        create_collection()

        if settings.qwen3_models_enabled:
            logger.info("Using GPU service for models (qwen3_models)")
        else:
            logger.info("Using local CPU models (embedded in backend)")
            try:
                from .core.model_loader import get_model_registry

                model_registry = get_model_registry()
                model_registry.load_models()
                logger.success("✅ Local models loaded successfully")
            except Exception as e:
                logger.warning(f"⚠️  Failed to load local models: {e}")

        # Initialize STT service
        try:
            from .services.stt_service import initialize_stt_service
            from .core.model_config import load_model_config

            config = load_model_config()
            stt_config = config.get("models", {}).get("stt", {})

            # STT now routes to GPU service, just initialize the proxy
            initialize_stt_service(
                model_name=stt_config.get("active", "turbo"),
                device=stt_config.get("device", "cuda"),
                compute_type=stt_config.get("compute_type", "float16"),
            )
            logger.info("✅ STT service initialized (routes to GPU service)")
        except Exception as e:
            logger.warning(
                f"⚠️  Failed to initialize STT service: {e}"
            )  # Initialize TTS service
        try:
            from .services.tts_service import initialize_tts_service
            import os

            api_key = os.getenv("ELEVENLABS_API_KEY")
            voice_id = os.getenv("ELEVENLABS_VOICE_ID")

            if api_key:
                initialize_tts_service(api_key=api_key, voice_id=voice_id)
                logger.success("✅ TTS service initialized successfully")
            else:
                logger.warning("⚠️  ElevenLabs API key not configured, TTS disabled")
        except Exception as e:
            logger.warning(f"⚠️  Failed to initialize TTS service: {e}")

        try:
            from .services.brain import qwen3_chat_complete, check_vllm_health

            logger.info("🔥 Warming up generation model (vLLM)...")

            # if check_vllm_health():
            warmup_messages = [
                {
                    "role": "system",
                    "content": "Bạn là Meddy - trợ lý y tế thông minh.",
                },
                {"role": "user", "content": "Chào Meddy!"},
            ]

            # Send a short warmup request
            response = qwen3_chat_complete(
                messages=warmup_messages,
                temperature=0.7,
                max_tokens=10,
            )

            if response:
                logger.success("✅ Generation model warmed up successfully")
            else:
                logger.warning("⚠️  Generation model warmup returned empty response")
            # else:
            #     logger.warning("⚠️  vLLM service not healthy, skipping warmup")
        except Exception as e:
            logger.warning(f"⚠️  Failed to warm up generation model: {e}")

        logger.info("Application startup complete.")
    except Exception as e:
        logger.error(f"Error during startup: {e}")
        raise


# Include routers
app.include_router(health.router)
app.include_router(rag.router)
app.include_router(models.router)
app.include_router(audio.router)
app.include_router(documents.router)


@app.get("/")
def read_root():
    return {
        "message": f"Welcome to the {settings.app_name} API!",
        "version": settings.app_version,
        "docs": "/docs",
        "routers": [
            "/v1/health",
            "/v1/rag",
            "/v1/models",
            "/v1/indexing",
            "/v1/documents",
            "/v1/audio",
        ],
    }
