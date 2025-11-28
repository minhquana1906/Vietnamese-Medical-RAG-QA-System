import asyncio
import hashlib
import os
import sys
import time
from pathlib import Path
from typing import List, Optional

import redis
import torch
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from faster_whisper import BatchedInferencePipeline, WhisperModel
from loguru import logger
from prometheus_client import Counter, Gauge, Histogram, make_asgi_app
from pydantic import BaseModel
from transformers import AutoModel, AutoModelForCausalLM, AutoTokenizer

# ============= LOGGING CONFIGURATION =============
# Remove default logger and add colorized output
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss.SSS}</green> | <level>{level: <7}</level> | <level>{message}</level>",
    level="INFO",
    colorize=True,
)

# Initialize FastAPI
app = FastAPI(
    title="Qwen3 Models + STT GPU Service",
    description="Serves Qwen3 Embedding, Reranker, Guardrails, and Whisper STT models on GPU",
    version="1.0.0",
)

# Prometheus metrics
gpu_memory_used_bytes = Gauge(
    "gpu_memory_used_bytes",
    "GPU VRAM allocated in bytes",
    ["device", "model_type"],
)

model_inference_duration_seconds = Histogram(
    "model_inference_duration_seconds",
    "Model inference duration",
    ["model_type", "model_name"],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
)

model_inference_total = Counter(
    "model_inference_total",
    "Total model inference requests",
    ["model_type", "model_name", "status"],
)

# Check GPU availability
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
logger.info(f"🚀 Using device: {DEVICE}")

if DEVICE == "cuda":
    logger.info(f"🎮 GPU: {torch.cuda.get_device_name(0)}")
    logger.info(
        f"💾 VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB"
    )

# Redis client for caching
REDIS_HOST = os.getenv("REDIS_HOST", "redis_db")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "redisadmin")

try:
    redis_client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD,
        decode_responses=False,
    )
    redis_client.ping()
    logger.info(f"✅ Redis connected: {REDIS_HOST}:{REDIS_PORT}")
except Exception as e:
    logger.warning(f"⚠️  Redis connection failed: {e}")
    redis_client = None

# Cache TTL
STT_CACHE_TTL = 3600  # 1 hour


class ModelRegistry:
    """Registry for all Qwen3 models + Whisper STT"""

    def __init__(self):
        self.embedding_model = None
        self.embedding_tokenizer = None

        self.reranker_model = None
        self.reranker_tokenizer = None
        self.reranker_token_true_id = None
        self.reranker_token_false_id = None
        self.reranker_prefix_tokens = None
        self.reranker_suffix_tokens = None

        self.guardrails_model = None
        self.guardrails_tokenizer = None

        self.whisper_model = None
        self.batched_whisper = None

        self.device = DEVICE
        self.loaded = False

    def load_models(self):
        """Load all models to GPU"""
        if self.loaded:
            logger.info("Models already loaded, skipping...")
            return

        try:
            # Load Embedding model
            logger.info("📦 Loading Qwen3-Embedding-0.6B...")
            embedding_model_name = os.getenv(
                "EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-0.6B"
            )
            self.embedding_tokenizer = AutoTokenizer.from_pretrained(
                embedding_model_name, padding_side="left"
            )
            self.embedding_model = AutoModel.from_pretrained(
                embedding_model_name,
                trust_remote_code=True,
                torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
            ).to(self.device)
            self.embedding_model.eval()
            logger.info(f"✅ Embedding model loaded on {self.device}")

            # Load Reranker model (MUST use AutoModelForCausalLM for yes/no generation)
            # Reference: https://huggingface.co/Qwen/Qwen3-Reranker-0.6B
            logger.info("📦 Loading Qwen3-Reranker-0.6B...")
            reranker_model_name = os.getenv(
                "RERANKER_MODEL", "Qwen/Qwen3-Reranker-0.6B"
            )
            self.reranker_tokenizer = AutoTokenizer.from_pretrained(
                reranker_model_name, padding_side="left"
            )
            self.reranker_model = AutoModelForCausalLM.from_pretrained(
                reranker_model_name,
                trust_remote_code=True,
                torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
            ).to(self.device)
            self.reranker_model.eval()

            # Pre-compute token IDs for scoring (official Qwen3-Reranker method)
            self.reranker_token_true_id = self.reranker_tokenizer.convert_tokens_to_ids(
                "yes"
            )
            self.reranker_token_false_id = (
                self.reranker_tokenizer.convert_tokens_to_ids("no")
            )

            # Pre-compute prefix/suffix tokens
            prefix = '<|im_start|>system\nJudge whether the Document meets the requirements based on the Query and the Instruct provided. Note that the answer can only be "yes" or "no".<|im_end|>\n<|im_start|>user\n'
            suffix = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
            self.reranker_prefix_tokens = self.reranker_tokenizer.encode(
                prefix, add_special_tokens=False
            )
            self.reranker_suffix_tokens = self.reranker_tokenizer.encode(
                suffix, add_special_tokens=False
            )
            logger.info(f"✅ Reranker model loaded on {self.device}")

            # Load Guardrails model (MUST use AutoModelForCausalLM for generation)
            logger.info("📦 Loading Qwen3Guard-Gen-0.6B...")
            guardrails_model_name = os.getenv(
                "GUARDRAILS_MODEL", "Qwen/Qwen3Guard-Gen-0.6B"
            )
            self.guardrails_tokenizer = AutoTokenizer.from_pretrained(
                guardrails_model_name
            )
            self.guardrails_model = AutoModelForCausalLM.from_pretrained(
                guardrails_model_name,
                trust_remote_code=True,
                torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
            ).to(self.device)
            self.guardrails_model.eval()
            logger.info(f"✅ Guardrails model loaded on {self.device}")

            # Load Whisper STT model with batch inference
            logger.info("📦 Loading Whisper-turbo for STT...")
            stt_model_name = os.getenv("STT_MODEL", "turbo")

            # Allow forcing STT device (e.g. to "cpu" to avoid cuDNN issues)
            stt_device = os.getenv("STT_DEVICE", self.device)
            compute_type = "float16" if stt_device == "cuda" else "int8"

            logger.info(f"🎤 STT Device: {stt_device}, Compute Type: {compute_type}")

            self.whisper_model = WhisperModel(
                stt_model_name,
                device=stt_device,
                compute_type=compute_type,
            )

            # Wrap in batched inference pipeline for better performance
            self.batched_whisper = BatchedInferencePipeline(model=self.whisper_model)
            logger.info(
                f"✅ Whisper-turbo loaded on {self.device} with compute_type={compute_type}"
            )

            self.loaded = True
            logger.success("🎉 All models loaded successfully!")

        except Exception as e:
            logger.error(f"❌ Failed to load models: {e}")
            raise


# Global model registry
registry = ModelRegistry()


@app.on_event("startup")
async def startup_event():
    """Load models on startup"""
    logger.info("🚀 Starting Qwen3 Models GPU Service...")
    registry.load_models()

    # Start GPU memory monitoring
    asyncio.create_task(update_gpu_memory_metrics())


async def update_gpu_memory_metrics():
    """Background task to update GPU memory metrics"""
    while True:
        try:
            if torch.cuda.is_available():
                for i in range(torch.cuda.device_count()):
                    device_name = f"cuda:{i}"
                    allocated = torch.cuda.memory_allocated(i)

                    # Update metrics for each model type
                    gpu_memory_used_bytes.labels(
                        device=device_name, model_type="embedding"
                    ).set(
                        allocated * 0.25
                    )  # Approximate split

                    gpu_memory_used_bytes.labels(
                        device=device_name, model_type="reranker"
                    ).set(allocated * 0.25)

                    gpu_memory_used_bytes.labels(
                        device=device_name, model_type="guardrails"
                    ).set(allocated * 0.25)

                    gpu_memory_used_bytes.labels(
                        device=device_name, model_type="stt"
                    ).set(allocated * 0.25)
        except Exception as e:
            logger.warning(f"Failed to update GPU metrics: {e}")

        await asyncio.sleep(30)  # Update every 30 seconds


# ============================================================================
# PYDANTIC SCHEMAS
# ============================================================================


class EmbedRequest(BaseModel):
    texts: List[str]
    normalize: bool = True
    is_query: bool = False
    instruction: Optional[str] = None


class EmbedResponse(BaseModel):
    embeddings: List[List[float]]
    model: str


class RerankRequest(BaseModel):
    query: str
    documents: List[str]
    top_n: int = 5
    instruction: Optional[str] = None


class RerankResponse(BaseModel):
    scores: List[float]
    indices: List[int]
    model: str


class GuardRequest(BaseModel):
    text: str
    check_type: str = "input"  # "input" or "output"
    query: Optional[str] = None


class GuardResponse(BaseModel):
    is_safe: bool
    severity: str
    categories: List[str]
    is_refusal: bool
    raw_output: str
    model: str


class SttResponse(BaseModel):
    """Speech-to-Text response"""

    text: str
    language: str
    duration: float
    cached: bool = False
    segments: Optional[List[dict]] = None


# ============================================================================
# ENDPOINTS
# ============================================================================


@app.get("/")
def root():
    return {
        "service": "Qwen3 Models + STT GPU Service",
        "device": DEVICE,
        "models_loaded": registry.loaded,
    }


@app.get("/health")
def health_check():
    """Health check endpoint"""
    if not registry.loaded:
        raise HTTPException(status_code=503, detail="Models not loaded")

    return {
        "status": "healthy",
        "device": DEVICE,
        "gpu_available": torch.cuda.is_available(),
        "models_loaded": True,
        "models": ["embedding", "reranker", "guardrails", "stt"],
    }


@app.get("/metrics")
def metrics():
    """Prometheus metrics endpoint"""
    from fastapi.responses import Response
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/v1/models/embed", response_model=EmbedResponse)
async def embed_endpoint(request: EmbedRequest):
    """Generate embeddings with Qwen3-Embedding"""
    if not registry.loaded:
        raise HTTPException(status_code=503, detail="Models not loaded")

    start_time = time.time()
    try:
        # Prepare instruction prefix (query vs document)
        if request.is_query:
            instruction = (
                request.instruction
                or "Given a medical query, retrieve relevant passages that answer the query"
            )
            texts = [
                f"Instruct: {instruction}\nQuery: {text}" for text in request.texts
            ]
        else:
            texts = request.texts

        # Tokenize and encode
        inputs = registry.embedding_tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        ).to(registry.device)

        # Generate embeddings
        with torch.no_grad():
            outputs = registry.embedding_model(**inputs)
            embeddings = outputs.last_hidden_state[:, 0]  # CLS token

            if request.normalize:
                embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)

        # Convert to list
        embeddings_list = embeddings.cpu().tolist()

        duration = time.time() - start_time
        logger.debug(
            f"✅ Embedded {len(request.texts)} texts in {duration:.3f}s on {DEVICE}"
        )

        # Record metrics
        model_inference_duration_seconds.labels(
            model_type="embedding", model_name="Qwen3-Embedding-0.6B"
        ).observe(duration)

        model_inference_total.labels(
            model_type="embedding", model_name="Qwen3-Embedding-0.6B", status="success"
        ).inc()

        return EmbedResponse(
            embeddings=embeddings_list,
            model="Qwen/Qwen3-Embedding-0.6B",
        )

    except Exception as e:
        logger.error(f"❌ Embedding error: {e}")
        model_inference_total.labels(
            model_type="embedding", model_name="Qwen3-Embedding-0.6B", status="error"
        ).inc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/models/rerank", response_model=RerankResponse)
async def rerank_endpoint(request: RerankRequest):
    """
    Rerank documents with Qwen3-Reranker using official method.

    Reference: https://huggingface.co/Qwen/Qwen3-Reranker-0.6B

    Method:
    1. Format: <Instruct>: {instruction}\n<Query>: {query}\n<Document>: {doc}
    2. System prompt: "Judge whether the Document meets the requirements..."
    3. Get logprobs for "yes" vs "no" tokens
    4. Score = softmax(yes_logit, no_logit)[1]

    Memory optimization:
    - Process in mini-batches to avoid OOM
    - Clear CUDA cache between batches
    - Reduced max_length for efficiency
    """
    if not registry.loaded:
        raise HTTPException(status_code=503, detail="Models not loaded")

    start_time = time.time()
    max_length = 2048
    mini_batch_size = 10  # Process 10 documents at a time to avoid OOM

    try:
        # Default instruction for medical RAG
        instruction = (
            request.instruction
            or "Given a medical question in Vietnamese, retrieve relevant medical passages that provide accurate information to answer the question"
        )

        # Format pairs: <Instruct>: {instruction}\n<Query>: {query}\n<Document>: {doc}
        pairs = [
            f"<Instruct>: {instruction}\n<Query>: {request.query}\n<Document>: {doc}"
            for doc in request.documents
        ]

        all_scores = []

        # Process in mini-batches to avoid OOM
        for batch_start in range(0, len(pairs), mini_batch_size):
            batch_end = min(batch_start + mini_batch_size, len(pairs))
            batch_pairs = pairs[batch_start:batch_end]

            # Tokenize with prefix/suffix (official method)
            inputs = registry.reranker_tokenizer(
                batch_pairs,
                padding=False,
                truncation=True,
                return_attention_mask=False,
                max_length=max_length
                - len(registry.reranker_prefix_tokens)
                - len(registry.reranker_suffix_tokens),
            )

            # Add prefix and suffix tokens
            for i, input_ids in enumerate(inputs["input_ids"]):
                inputs["input_ids"][i] = (
                    registry.reranker_prefix_tokens
                    + input_ids
                    + registry.reranker_suffix_tokens
                )

            # Pad and convert to tensors
            inputs = registry.reranker_tokenizer.pad(
                inputs, padding=True, return_tensors="pt", max_length=max_length
            )
            inputs = {k: v.to(registry.device) for k, v in inputs.items()}

            # Get logits for yes/no tokens (official scoring method)
            with torch.no_grad():
                outputs = registry.reranker_model(**inputs)
                # Get logits at the last position
                batch_logits = outputs.logits[:, -1, :]

                # Extract yes/no logits
                true_logits = batch_logits[:, registry.reranker_token_true_id]
                false_logits = batch_logits[:, registry.reranker_token_false_id]

                # Stack and apply log_softmax, then get probability of "yes"
                stacked = torch.stack([false_logits, true_logits], dim=1)
                log_probs = torch.nn.functional.log_softmax(stacked, dim=1)
                batch_scores = log_probs[:, 1].exp()  # P(yes)

                all_scores.extend(batch_scores.cpu().tolist())

            # Clear tensors and CUDA cache to free memory
            del (
                inputs,
                outputs,
                batch_logits,
                true_logits,
                false_logits,
                stacked,
                log_probs,
                batch_scores,
            )
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        # Sort by score descending
        sorted_pairs = sorted(enumerate(all_scores), key=lambda x: x[1], reverse=True)

        # Get top-n
        top_indices = [idx for idx, _ in sorted_pairs[: request.top_n]]
        top_scores = [score for _, score in sorted_pairs[: request.top_n]]

        duration = time.time() - start_time
        logger.info(
            f"[RERANK] ✅ {len(request.documents)} docs → top scores: {[f'{s:.3f}' for s in top_scores[:3]]} | {duration:.3f}s"
        )

        # Record metrics
        model_inference_duration_seconds.labels(
            model_type="reranker", model_name="Qwen3-Reranker-0.6B"
        ).observe(duration)

        model_inference_total.labels(
            model_type="reranker", model_name="Qwen3-Reranker-0.6B", status="success"
        ).inc()

        return RerankResponse(
            scores=top_scores,
            indices=top_indices,
            model="Qwen/Qwen3-Reranker-0.6B",
        )

    except Exception as e:
        logger.error(f"❌ Reranking error: {e}")
        model_inference_total.labels(
            model_type="reranker", model_name="Qwen3-Reranker-0.6B", status="error"
        ).inc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/models/guard", response_model=GuardResponse)
async def guard_endpoint(request: GuardRequest):
    """Check content safety with Qwen3Guard"""
    if not registry.loaded:
        raise HTTPException(status_code=503, detail="Models not loaded")

    start_time = time.time()
    try:
        # Build messages for chat template (following official Qwen3Guard pattern)
        if request.check_type == "input":
            messages = [{"role": "user", "content": request.text}]
        else:  # output
            messages = [
                {"role": "user", "content": request.query or ""},
                {"role": "assistant", "content": request.text},
            ]

        # Apply chat template and tokenize (official method)
        text = registry.guardrails_tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=False
        )
        inputs = registry.guardrails_tokenizer(
            [text],
            return_tensors="pt",
            max_length=512,
            truncation=True,
        ).to(registry.device)

        # Debug: Log input shape
        logger.debug(f"Input IDs shape: {inputs.input_ids.shape}")

        # Generate safety check
        with torch.no_grad():
            generated_ids = registry.guardrails_model.generate(
                **inputs,
                max_new_tokens=128,  # Increased per docs
                do_sample=False,  # Removed temperature for greedy decoding
            )

        # Debug: Log output shape
        logger.debug(f"Generated IDs shape: {generated_ids.shape}")
        logger.debug(f"Input length: {len(inputs.input_ids[0])}")

        # Extract only generated tokens (skip input tokens)
        output_ids = generated_ids[0][len(inputs.input_ids[0]) :]
        raw_output = registry.guardrails_tokenizer.decode(
            output_ids,
            skip_special_tokens=True,
        ).strip()

        # Debug: Log generated output
        logger.debug(f"Raw output: {raw_output[:200]}")

        # Parse output (format: "Safety: Safe/Unsafe\nCategories: ...")
        is_safe = "safe" in raw_output.lower() and "unsafe" not in raw_output.lower()

        # Extract severity
        if "unsafe" in raw_output.lower():
            severity = "high"
        elif "controversial" in raw_output.lower():
            severity = "medium"
        else:
            severity = "low"

        # Extract categories (with safety check)
        categories = []
        try:
            if "categories:" in raw_output.lower():
                parts = raw_output.lower().split("categories:", 1)
                if len(parts) > 1:
                    cat_text = parts[1].strip()
                    if cat_text and cat_text != "none":
                        categories = [
                            c.strip() for c in cat_text.split(",") if c.strip()
                        ]
        except Exception as e:
            logger.warning(f"Failed to parse categories: {e}")

        # Check for refusal
        is_refusal = any(
            word in request.text.lower()
            for word in ["sorry", "cannot", "can't", "unable"]
        )

        duration = time.time() - start_time
        logger.debug(
            f"✅ Guard check in {duration:.3f}s: safe={is_safe}, severity={severity}"
        )

        # Record metrics
        model_inference_duration_seconds.labels(
            model_type="guardrails", model_name="Qwen3Guard-Gen-0.6B"
        ).observe(duration)

        model_inference_total.labels(
            model_type="guardrails", model_name="Qwen3Guard-Gen-0.6B", status="success"
        ).inc()

        return GuardResponse(
            is_safe=is_safe,
            severity=severity,
            categories=categories,
            is_refusal=is_refusal,
            raw_output=raw_output,
            model="Qwen/Qwen3Guard-Gen-0.6B",
        )

    except Exception as e:
        logger.error(f"❌ Guardrails error: {e}")
        model_inference_total.labels(
            model_type="guardrails", model_name="Qwen3Guard-Gen-0.6B", status="error"
        ).inc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/models/stt", response_model=SttResponse)
async def stt_endpoint(
    file: UploadFile = File(...),
    language: str = Form("vi"),
    batch_size: int = Form(16),
):
    """
    Speech-to-Text endpoint with batched inference

    Uses Whisper-turbo with BatchedInferencePipeline for optimal GPU utilization
    """
    if not registry.loaded:
        raise HTTPException(status_code=503, detail="Models not loaded")

    audio_path = None
    start_time = time.time()
    try:
        # Save uploaded file temporarily
        audio_dir = Path("/tmp/audio")
        audio_dir.mkdir(parents=True, exist_ok=True)
        audio_path = audio_dir / f"stt_{int(time.time())}_{file.filename}"

        with open(audio_path, "wb") as f:
            content = await file.read()
            f.write(content)

        logger.info(
            f"📥 STT request: file={file.filename}, size={len(content)}, language={language}"
        )

        # Check cache first
        audio_hash = hashlib.sha256(content).hexdigest()
        cache_key = f"stt:transcript:{audio_hash}"

        cached_transcript = None
        if redis_client:
            try:
                cached = redis_client.get(cache_key)
                if cached:
                    cached_transcript = cached.decode("utf-8")
                    logger.info(f"🎯 STT cache hit: {audio_hash[:16]}...")
            except Exception as e:
                logger.warning(f"Redis get failed: {e}")

        if cached_transcript:
            return SttResponse(
                text=cached_transcript,
                language=language,
                duration=0.0,
                cached=True,
            )

        # Transcribe with batched inference
        logger.info(f"🎤 Transcribing with Whisper-turbo (batch_size={batch_size})...")

        segments, info = registry.batched_whisper.transcribe(
            str(audio_path),
            language=language,
            batch_size=batch_size,
        )

        # Collect segments
        segment_list = []
        full_text = ""

        for segment in segments:
            segment_text = segment.text.strip()
            full_text += segment_text + " "
            segment_list.append(
                {
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment_text,
                }
            )

        full_text = full_text.strip()

        # Cache the transcript
        if redis_client and audio_hash:
            try:
                redis_client.setex(cache_key, STT_CACHE_TTL, full_text.encode("utf-8"))
                logger.info(f"💾 STT transcript cached: {audio_hash[:16]}...")
            except Exception as e:
                logger.warning(f"Redis set failed: {e}")

        duration = time.time() - start_time
        logger.info(
            f"✅ STT complete: length={len(full_text)}, segments={len(segment_list)}, duration={duration:.3f}s"
        )

        # Record metrics
        model_inference_duration_seconds.labels(
            model_type="stt", model_name="whisper-turbo"
        ).observe(duration)

        model_inference_total.labels(
            model_type="stt", model_name="whisper-turbo", status="success"
        ).inc()

        return SttResponse(
            text=full_text,
            language=info.language,
            duration=info.duration,
            cached=False,
            segments=segment_list,
        )

    except Exception as e:
        logger.error(f"❌ STT error: {e}")
        model_inference_total.labels(
            model_type="stt", model_name="whisper-turbo", status="error"
        ).inc()
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        # Cleanup temporary file
        if audio_path and audio_path.exists():
            try:
                audio_path.unlink()
            except Exception as e:
                logger.warning(f"Failed to delete temp audio file: {e}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8002)
