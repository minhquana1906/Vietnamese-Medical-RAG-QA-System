from fastapi import FastAPI
from loguru import logger
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import make_asgi_app

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

        if settings.qwen3_models_enabled:
            logger.info("Using GPU service for models (qwen3_models)")
        else:
            logger.info("Using local CPU models (embedded in backend)")
            try:
                from .core.model_loader import get_model_registry

                model_registry = get_model_registry()
                model_registry.load_models()
                logger.info("✅ Local models loaded successfully")
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
                logger.info("✅ TTS service initialized successfully")
            else:
                logger.warning("⚠️  ElevenLabs API key not configured, TTS disabled")
        except Exception as e:
            logger.warning(f"⚠️  Failed to initialize TTS service: {e}")

        # Warm up generation model (vLLM) to reduce first request latency
        try:
            from .services.brain import qwen3_chat_complete, check_vllm_health

            logger.info("🔥 Warming up generation model (vLLM)...")

            # Check if vLLM is healthy first
            if check_vllm_health():
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
                    use_fallback=False,
                )

                if response:
                    logger.info("✅ Generation model warmed up successfully")
                else:
                    logger.warning("⚠️  Generation model warmup returned empty response")
            else:
                logger.warning("⚠️  vLLM service not healthy, skipping warmup")
        except Exception as e:
            logger.warning(f"⚠️  Failed to warm up generation model: {e}")
            # Don't raise - warmup failure shouldn't prevent app startup

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
