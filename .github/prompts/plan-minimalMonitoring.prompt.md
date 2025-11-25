# Plan: Minimal MVP Monitoring - Essential Observability với Template Reuse

Monitoring tối giản nhưng ĐÚNG TRỌNG TÂM cho MVP: Metrics/logs/traces quan trọng + reuse Grafana templates + visualize đầy đủ model performance (generation/embedding/rerank/guardrails). Tránh over-engineering nhưng vẫn đủ visibility để debug.

## Philosophy: "Essential but Complete Model Observability"

**Core Focus**:
- ✅ Full model metrics: Generation (vLLM), Embedding, Rerank, Guardrails (GPU service)
- ✅ Voice pipeline metrics: STT, TTS, Audio RAG latency breakdown
- ✅ Logs từ ALL containers (auto-collected)
- ✅ Basic tracing cho critical paths
- ✅ **3 imported templates** (FastAPI #16110, Loki #13639, vLLM #23991) + 1 custom dashboard

**Strategic Skips** (add later nếu cần):
- ❌ Infrastructure exporters (Redis, ES, Node) - monitor manual khi issue
- ❌ JSON logging - console logs đủ cho MVP
- ❌ Complex alert rules - 1 simple alert
- ❌ Per-model fine-grained metrics (token/s, cache hit rates) - observe latency thôi

**Result**: ~8-10 hours implementation, full model visibility, enough để debug issues.

---

## Current State Analysis

**Monitoring Stack**: ✅ Đã có nhưng **config chưa đủ**
- Prometheus: Scraping backend + vLLM, nhưng **thiếu GPU service target**
- Loki: Running nhưng **Promtail chưa config Docker auto-discovery đúng**
- Tempo: Configured nhưng **chưa propagate traces qua services**
- Grafana: Datasources OK, nhưng **dashboards = empty placeholders**

**Backend Instrumentation**: ✅ Cơ bản đã có
- Metrics: `model_inference_duration_seconds` đã có cho embedding/rerank trong `metrics.py`
- Tracing: OpenTelemetry setup trong `main.py`
- Logging: Loguru with console output

**GPU Service**: ❌ Không có metrics endpoint
- Serving embedding, rerank, guard, STT models
- Cần add `/metrics` endpoint để Prometheus scrape

**Voice Pipeline**: ⚠️ Metrics thiếu
- STT/TTS services có logging nhưng không có Prometheus metrics
- Audio RAG endpoint chưa có latency breakdown

---

## Implementation Steps (Minimal but Complete)

### Step 1: Fix Monitoring Stack Configuration

**Files**: [`monitoring/prometheus/prometheus.yml`], [`monitoring/promtail/promtail-config.yaml`], [`monitoring/docker-compose.yml`]

#### 1.1 Add GPU Service Scrape Target

**Update `monitoring/prometheus/prometheus.yml`**:

```yaml
scrape_configs:
  - job_name: 'backend'
    static_configs:
      - targets: ['chatbot_api:8000']
    scrape_interval: 10s
    metrics_path: '/metrics'

  - job_name: 'vllm'
    static_configs:
      - targets: ['vllm:8000']
    scrape_interval: 10s
    metrics_path: '/metrics'

  # ADD THIS - GPU service metrics
  - job_name: 'gpu_service'
    static_configs:
      - targets: ['extra_models_gpu:8002']
    scrape_interval: 15s  # Slightly longer for GPU
    metrics_path: '/metrics'

  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']
    scrape_interval: 15s
```

#### 1.2 Fix Promtail Docker Auto-Discovery

**Update `monitoring/promtail/promtail-config.yaml`**:

```yaml
server:
  http_listen_port: 9080
  grpc_listen_port: 0

positions:
  filename: /tmp/positions.yaml

clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:
  # Remove file-based backend scraping (không cần file logs)
  
  # AUTO-COLLECT ALL DOCKER CONTAINERS
  - job_name: docker_containers
    docker_sd_configs:
      - host: unix:///var/run/docker.sock
        refresh_interval: 10s
    relabel_configs:
      # Extract container name
      - source_labels: ['__meta_docker_container_name']
        regex: '/(.*)'
        target_label: 'container'
      
      # Extract log stream (stdout/stderr)
      - source_labels: ['__meta_docker_container_log_stream']
        target_label: 'stream'
      
      # Extract service name from compose label
      - source_labels: ['__meta_docker_container_label_com_docker_compose_service']
        target_label: 'service'
      
      # Extract project name
      - source_labels: ['__meta_docker_container_label_com_docker_compose_project']
        target_label: 'project'
```

**Verify Docker socket mount** trong `monitoring/docker-compose.yml`:

```yaml
promtail:
  image: grafana/promtail:3.5
  container_name: promtail
  restart: always
  volumes:
    - ./promtail/promtail-config.yaml:/etc/promtail/config.yaml
    - /var/run/docker.sock:/var/run/docker.sock:ro  # Ensure this exists
    - ~/docker_data/containers:/var/lib/docker/containers:ro
  command: -config.file=/etc/promtail/config.yaml
  networks:
    - medical_rag_network
  depends_on:
    - loki
```

**Restart to apply**:
```bash
cd monitoring
docker compose restart prometheus promtail
```

---

### Step 2: Add GPU Service Metrics Endpoint

**Files**: [`serving/qwen3_models/app.py`], [`serving/qwen3_models/requirements.txt`]

#### 2.1 Install Prometheus Client

**Update `serving/qwen3_models/requirements.txt`**:
```txt
fastapi==0.115.3
uvicorn==0.32.1
torch==2.5.1
transformers==4.48.2
sentence-transformers==3.3.1
faster-whisper==1.1.0
redis==5.2.1
prometheus-client==0.21.0  # ADD THIS
# ... existing deps ...
```

#### 2.2 Instrument GPU Service

**Update `serving/qwen3_models/app.py`**:

```python
from fastapi import FastAPI
from prometheus_client import Gauge, Histogram, Counter, make_asgi_app
import torch
import asyncio

app = FastAPI(title="Qwen3 Models + Whisper-turbo GPU Service")

# Prometheus metrics
gpu_memory_used_bytes = Gauge(
    "gpu_memory_used_bytes",
    "GPU VRAM allocated in bytes",
    ["device", "model_type"]
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
    ["model_type", "model_name", "status"],  # status: success/error
)

# Mount Prometheus metrics endpoint at /metrics
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# Background task to update GPU memory metrics
@app.on_event("startup")
async def start_gpu_monitoring():
    async def update_gpu_memory():
        while True:
            try:
                if torch.cuda.is_available():
                    # Track memory per model type
                    embedding_memory = torch.cuda.memory_allocated(0) if hasattr(app.state, 'embedding_model') else 0
                    gpu_memory_used_bytes.labels(device="cuda:0", model_type="embedding").set(embedding_memory)
                    
                    # Total GPU memory
                    total_memory = torch.cuda.memory_allocated(0)
                    gpu_memory_used_bytes.labels(device="cuda:0", model_type="total").set(total_memory)
            except Exception as e:
                logger.error(f"GPU monitoring error: {e}")
            
            await asyncio.sleep(30)  # Update every 30s
    
    asyncio.create_task(update_gpu_memory())

# Instrument existing endpoints
@app.post("/embed")
async def embed_texts(request: EmbedRequest):
    import time
    start = time.time()
    
    try:
        # ... existing embedding code ...
        embeddings = await embedding_service.embed(request.texts)
        
        duration = time.time() - start
        model_inference_duration_seconds.labels(
            model_type="embedding", 
            model_name="Qwen3-Embedding-0.6B"
        ).observe(duration)
        
        model_inference_total.labels(
            model_type="embedding",
            model_name="Qwen3-Embedding-0.6B",
            status="success"
        ).inc()
        
        return {"embeddings": embeddings}
    
    except Exception as e:
        model_inference_total.labels(
            model_type="embedding",
            model_name="Qwen3-Embedding-0.6B",
            status="error"
        ).inc()
        raise

@app.post("/rerank")
async def rerank_texts(request: RerankRequest):
    import time
    start = time.time()
    
    try:
        # ... existing rerank code ...
        scores = await rerank_service.rerank(request.query, request.texts)
        
        duration = time.time() - start
        model_inference_duration_seconds.labels(
            model_type="rerank",
            model_name="Qwen3-Reranker-0.6B"
        ).observe(duration)
        
        model_inference_total.labels(
            model_type="rerank",
            model_name="Qwen3-Reranker-0.6B",
            status="success"
        ).inc()
        
        return {"scores": scores}
    
    except Exception as e:
        model_inference_total.labels(
            model_type="rerank",
            model_name="Qwen3-Reranker-0.6B",
            status="error"
        ).inc()
        raise

@app.post("/guard")
async def guard_text(request: GuardRequest):
    import time
    start = time.time()
    
    try:
        # ... existing guard code ...
        result = await guard_service.validate(request.text)
        
        duration = time.time() - start
        model_inference_duration_seconds.labels(
            model_type="guardrails",
            model_name="Qwen3Guard-Gen-0.6B"
        ).observe(duration)
        
        model_inference_total.labels(
            model_type="guardrails",
            model_name="Qwen3Guard-Gen-0.6B",
            status="success"
        ).inc()
        
        return result
    
    except Exception as e:
        model_inference_total.labels(
            model_type="guardrails",
            model_name="Qwen3Guard-Gen-0.6B",
            status="error"
        ).inc()
        raise

@app.post("/stt")
async def speech_to_text(file: UploadFile):
    import time
    start = time.time()
    
    try:
        # ... existing STT code ...
        transcript = await stt_service.transcribe(audio_bytes)
        
        duration = time.time() - start
        model_inference_duration_seconds.labels(
            model_type="stt",
            model_name="whisper-turbo"
        ).observe(duration)
        
        model_inference_total.labels(
            model_type="stt",
            model_name="whisper-turbo",
            status="success"
        ).inc()
        
        return {"transcript": transcript}
    
    except Exception as e:
        model_inference_total.labels(
            model_type="stt",
            model_name="whisper-turbo",
            status="error"
        ).inc()
        raise

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "gpu_available": torch.cuda.is_available(),
        "gpu_count": torch.cuda.device_count() if torch.cuda.is_available() else 0,
        "models_loaded": {
            "embedding": hasattr(app.state, 'embedding_model'),
            "rerank": hasattr(app.state, 'rerank_model'),
            "guard": hasattr(app.state, 'guard_model'),
            "stt": hasattr(app.state, 'stt_model'),
        }
    }
```

**Verify**:
```bash
docker compose restart extra_models
curl http://localhost:8002/metrics | grep model_inference
curl http://localhost:8002/health
```

---

### Step 3: Add Voice Pipeline Metrics (Backend)

**Files**: [`backend/src/core/metrics.py`], [`backend/src/routers/audio.py`]

#### 3.1 Define Voice Metrics

**Update `backend/src/core/metrics.py`**:

```python
from prometheus_client import Counter, Histogram, Gauge

# ... existing metrics ...

# Voice processing metrics (minimal but essential)
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
```

#### 3.2 Instrument Audio Endpoints

**Update `backend/src/routers/audio.py`**:

```python
from ..core.metrics import (
    voice_request_duration_seconds,
    audio_rag_stage_duration_seconds,
    voice_request_errors_total,
)
import time

@router.post("/v1/models/stt")
async def speech_to_text(file: UploadFile):
    start = time.time()
    try:
        # ... existing STT code ...
        result = await stt_service.transcribe(audio_bytes)
        return result
    except Exception as e:
        voice_request_errors_total.labels(
            endpoint="stt",
            error_type=type(e).__name__
        ).inc()
        raise
    finally:
        voice_request_duration_seconds.labels(endpoint="stt").observe(
            time.time() - start
        )

@router.post("/v1/models/tts")
async def text_to_speech(request: TTSRequest):
    start = time.time()
    try:
        # ... existing TTS code ...
        return audio_response
    except Exception as e:
        voice_request_errors_total.labels(
            endpoint="tts",
            error_type=type(e).__name__
        ).inc()
        raise
    finally:
        voice_request_duration_seconds.labels(endpoint="tts").observe(
            time.time() - start
        )

@router.post("/v1/rag/audio")
async def audio_rag_query(
    file: UploadFile,
    user_identifier: str,
    thread_id: str,
):
    request_start = time.time()
    
    try:
        audio_bytes = await file.read()
        
        # Stage 1: STT
        stage_start = time.time()
        transcript = await stt_service.transcribe(audio_bytes)
        audio_rag_stage_duration_seconds.labels(stage="stt").observe(
            time.time() - stage_start
        )
        
        # Stage 2: RAG
        stage_start = time.time()
        from ..services.rag_service import rag_service
        rag_result = await rag_service.query(
            user_identifier=user_identifier,
            thread_id=thread_id,
            query=transcript,
        )
        audio_rag_stage_duration_seconds.labels(stage="rag").observe(
            time.time() - stage_start
        )
        
        # Stage 3: TTS
        stage_start = time.time()
        audio_path = await tts_service.synthesize(rag_result["answer"])
        audio_rag_stage_duration_seconds.labels(stage="tts").observe(
            time.time() - stage_start
        )
        
        return FileResponse(audio_path, media_type="audio/mpeg")
    
    except Exception as e:
        voice_request_errors_total.labels(
            endpoint="audio_rag",
            error_type=type(e).__name__
        ).inc()
        raise
    finally:
        voice_request_duration_seconds.labels(endpoint="audio_rag").observe(
            time.time() - request_start
        )
```

---

### Step 4: Add Detailed RAG Pipeline Tracing (Text + Audio)

**Files**: [`backend/src/tasks.py`], [`backend/src/routers/rag.py`], [`backend/src/routers/audio.py`]

#### 4.1 Add Tracing to Core RAG Pipeline (Text Queries)

**Update `backend/src/tasks.py`** - Instrument message_handler_task với detailed spans:

```python
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

tracer = trace.get_tracer(__name__)

@celery_app.task(bind=True, name="message_handler_task")
def message_handler_task(
    self,
    user_identifier: str,
    thread_id: str,
    query: str,
) -> dict:
    """RAG pipeline with detailed tracing"""
    
    with tracer.start_as_current_span("rag_pipeline") as span:
        span.set_attribute("user_identifier", user_identifier)
        span.set_attribute("thread_id", thread_id)
        span.set_attribute("query", query[:100])  # Truncate for privacy
        
        try:
            # Stage 1: Query Enhancement
            with tracer.start_as_current_span("query_enhancement") as enh_span:
                enhanced_query = enhance_query_quality(query)
                enh_span.set_attribute("enhanced_query", enhanced_query[:100])
            
            # Stage 2: Embedding Generation
            with tracer.start_as_current_span("embedding_generation") as emb_span:
                query_embedding = embedding_service.embed_text(enhanced_query)
                emb_span.set_attribute("embedding_dim", len(query_embedding))
            
            # Stage 3: Hybrid Search (Vector + Keyword)
            with tracer.start_as_current_span("hybrid_search") as search_span:
                # Vector search
                with tracer.start_as_current_span("vector_search") as vec_span:
                    vector_results = qdrant_client.search(
                        collection_name="medical_chunks",
                        query_vector=query_embedding,
                        limit=20,
                    )
                    vec_span.set_attribute("vector_results_count", len(vector_results))
                
                # Keyword search
                with tracer.start_as_current_span("keyword_search") as kw_span:
                    keyword_results = elasticsearch_service.search_bm25(
                        query=enhanced_query,
                        limit=20,
                    )
                    kw_span.set_attribute("keyword_results_count", len(keyword_results))
                
                # RRF Fusion
                with tracer.start_as_current_span("rrf_fusion") as rrf_span:
                    fused_results = hybrid_search.rrf_fusion(
                        vector_results, keyword_results, k=60
                    )
                    rrf_span.set_attribute("fused_count", len(fused_results))
                    search_span.set_attribute("final_candidates", len(fused_results))
            
            # Stage 4: Reranking
            with tracer.start_as_current_span("reranking") as rerank_span:
                reranked_chunks = rerank_service.rerank(
                    query=enhanced_query,
                    chunks=[r["content"] for r in fused_results[:10]],
                )
                rerank_span.set_attribute("reranked_count", len(reranked_chunks))
                rerank_span.set_attribute("top_score", reranked_chunks[0]["score"] if reranked_chunks else 0)
            
            # Stage 5: Context Building
            with tracer.start_as_current_span("context_building") as ctx_span:
                context = "\n\n".join([
                    f"[Chunk {i+1}] {chunk['content']}" 
                    for i, chunk in enumerate(reranked_chunks[:5])
                ])
                ctx_span.set_attribute("context_length", len(context))
                ctx_span.set_attribute("chunks_used", len(reranked_chunks[:5]))
            
            # Stage 6: Input Guardrails
            with tracer.start_as_current_span("input_guardrails") as guard_span:
                guard_result = guardrails_service.validate_input(query)
                guard_span.set_attribute("is_safe", guard_result["is_safe"])
                if not guard_result["is_safe"]:
                    guard_span.set_attribute("violation_type", guard_result["violation_type"])
                    span.set_status(Status(StatusCode.ERROR, "Input validation failed"))
                    return {
                        "answer": "Xin lỗi, câu hỏi này vi phạm quy tắc an toàn.",
                        "chunks": [],
                        "status": "rejected_by_guardrails"
                    }
            
            # Stage 7: Generation
            with tracer.start_as_current_span("generation") as gen_span:
                prompt = f"""Dựa vào ngữ cảnh sau, hãy trả lời câu hỏi của người dùng:

Ngữ cảnh:
{context}

Câu hỏi: {query}

Trả lời:"""
                
                response = brain_service.generate(
                    prompt=prompt,
                    max_tokens=512,
                    temperature=0.7,
                )
                
                gen_span.set_attribute("response_length", len(response))
                gen_span.set_attribute("prompt_tokens", len(prompt.split()))
                gen_span.set_attribute("response_tokens", len(response.split()))
            
            # Stage 8: Output Guardrails
            with tracer.start_as_current_span("output_guardrails") as out_guard_span:
                output_guard_result = guardrails_service.validate_output(response)
                out_guard_span.set_attribute("is_safe", output_guard_result["is_safe"])
                if not output_guard_result["is_safe"]:
                    out_guard_span.set_attribute("violation_type", output_guard_result["violation_type"])
                    response = "Xin lỗi, tôi không thể tạo ra câu trả lời an toàn cho câu hỏi này."
            
            span.set_status(Status(StatusCode.OK))
            return {
                "answer": response,
                "chunks": reranked_chunks[:5],
                "status": "success",
            }
        
        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
            logger.error(f"RAG pipeline error: {e}")
            raise
```

#### 4.2 Add Tracing to RAG Router (Text Entry Point)

**Update `backend/src/routers/rag.py`**:

```python
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

@router.post("/v1/rag")
async def rag_query(request: RAGRequest):
    """RAG query endpoint with tracing"""
    
    with tracer.start_as_current_span("rag_api_request") as span:
        span.set_attribute("user_identifier", request.user_identifier)
        span.set_attribute("thread_id", request.thread_id)
        span.set_attribute("query_length", len(request.query))
        
        try:
            # Dispatch to Celery task
            task = message_handler_task.delay(
                user_identifier=request.user_identifier,
                thread_id=request.thread_id,
                query=request.query,
            )
            
            # Wait for result (or use AsyncResult for async)
            result = task.get(timeout=30)
            
            span.set_attribute("chunks_returned", len(result.get("chunks", [])))
            span.set_attribute("status", result.get("status", "unknown"))
            
            return result
        
        except Exception as e:
            span.record_exception(e)
            raise
```

#### 4.3 Add Tracing to Audio RAG (Voice Entry Point)

**Update `backend/src/routers/audio.py`**:

```python
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

tracer = trace.get_tracer(__name__)

@router.post("/v1/rag/audio")
async def audio_rag_query(
    file: UploadFile,
    user_identifier: str,
    thread_id: str,
):
    """Audio RAG with detailed tracing (STT → RAG → TTS)"""
    
    with tracer.start_as_current_span("audio_rag_query") as span:
        span.set_attribute("user_identifier", user_identifier)
        span.set_attribute("thread_id", thread_id)
        
        request_start = time.time()
        
        try:
            # Stage 1: Audio Upload
            with tracer.start_as_current_span("audio_upload") as upload_span:
                audio_bytes = await file.read()
                upload_span.set_attribute("audio_size_bytes", len(audio_bytes))
                upload_span.set_attribute("audio_format", file.content_type)
            
            # Stage 2: STT (Speech-to-Text)
            with tracer.start_as_current_span("stt_transcribe") as stt_span:
                stage_start = time.time()
                transcript = await stt_service.transcribe(audio_bytes)
                stt_duration = time.time() - stage_start
                
                stt_span.set_attribute("transcript_length", len(transcript))
                stt_span.set_attribute("duration_seconds", stt_duration)
                audio_rag_stage_duration_seconds.labels(stage="stt").observe(stt_duration)
            
            # Stage 3: RAG Pipeline (reuse core RAG with tracing)
            with tracer.start_as_current_span("rag_processing") as rag_span:
                stage_start = time.time()
                
                # Dispatch to message_handler_task (which has detailed tracing)
                task = message_handler_task.delay(
                    user_identifier=user_identifier,
                    thread_id=thread_id,
                    query=transcript,
                )
                rag_result = task.get(timeout=30)
                
                rag_duration = time.time() - stage_start
                rag_span.set_attribute("chunks_retrieved", len(rag_result.get("chunks", [])))
                rag_span.set_attribute("answer_length", len(rag_result.get("answer", "")))
                rag_span.set_attribute("duration_seconds", rag_duration)
                audio_rag_stage_duration_seconds.labels(stage="rag").observe(rag_duration)
            
            # Stage 4: TTS (Text-to-Speech)
            with tracer.start_as_current_span("tts_synthesize") as tts_span:
                stage_start = time.time()
                audio_path = await tts_service.synthesize(rag_result["answer"])
                tts_duration = time.time() - stage_start
                
                tts_span.set_attribute("audio_path", audio_path)
                tts_span.set_attribute("input_text_length", len(rag_result["answer"]))
                tts_span.set_attribute("duration_seconds", tts_duration)
                audio_rag_stage_duration_seconds.labels(stage="tts").observe(tts_duration)
            
            # Success
            span.set_status(Status(StatusCode.OK))
            total_duration = time.time() - request_start
            span.set_attribute("total_duration_seconds", total_duration)
            
            return FileResponse(audio_path, media_type="audio/mpeg")
        
        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
            voice_request_errors_total.labels(
                endpoint="audio_rag",
                error_type=type(e).__name__
            ).inc()
            raise
        finally:
            voice_request_duration_seconds.labels(endpoint="audio_rag").observe(
                time.time() - request_start
            )
```

**Key Improvements**:
- ✅ **Text RAG**: 8 detailed spans (query_enhancement, embedding, vector_search, keyword_search, rrf_fusion, reranking, context_building, input_guardrails, generation, output_guardrails)
- ✅ **Audio RAG**: Reuses core RAG tracing + adds STT/TTS spans
- ✅ **Attributes**: Rich context (counts, scores, durations, safety checks)
- ✅ **Error handling**: Exceptions recorded in spans

---

### Step 5: Import Grafana Dashboard Templates

**Files**: [`monitoring/grafana/dashboards/`]

#### 5.1 Create Provisioning Config

**Create `monitoring/grafana/dashboards/dashboards.yaml`**:

```yaml
apiVersion: 1

providers:
  - name: 'Default'
    orgId: 1
    folder: ''
    type: file
    disableDeletion: false
    updateIntervalSeconds: 10
    allowUiUpdates: true
    options:
      path: /etc/grafana/provisioning/dashboards
      foldersFromFilesStructure: false
```

#### 5.2 Download Templates

```bash
cd monitoring/grafana/dashboards/

# FastAPI Dashboard #16110
curl -L "https://grafana.com/api/dashboards/16110/revisions/1/download" \
  -o fastapi_template.json

# Loki Dashboard #13639
curl -L "https://grafana.com/api/dashboards/13639/revisions/2/download" \
  -o loki_template.json

# vLLM Dashboard #23991 (if exists, else use placeholder)
curl -L "https://grafana.com/api/dashboards/23991/revisions/1/download" \
  -o vllm_template.json 2>/dev/null || echo '{"dashboard": {"title": "vLLM Metrics", "panels": []}}' > vllm_template.json
```

#### 5.3 Update Grafana docker compose Mount

**Ensure `monitoring/docker-compose.yml` has**:

```yaml
grafana:
  image: grafana/grafana:12.2.0
  container_name: grafana
  restart: always
  ports:
    - "3000:3000"
  environment:
    - GF_SECURITY_ADMIN_USER=${GRAFANA_ADMIN_USER:-admin}
    - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_ADMIN_PASSWORD:-admin}
    - GF_USERS_ALLOW_SIGN_UP=false
  volumes:
    - ./grafana/dashboards:/etc/grafana/provisioning/dashboards  # Templates auto-import
    - ./grafana/datasources.yaml:/etc/grafana/provisioning/datasources/datasources.yaml
    - grafana_data:/var/lib/grafana
  networks:
    - medical_rag_network
  depends_on:
    - prometheus
    - loki
    - tempo
```

**Restart Grafana**:
```bash
docker compose restart grafana
```

---

### Step 6: Build Custom Model Monitoring Dashboard

**Files**: [`monitoring/grafana/dashboards/model_monitoring.json`]

**Create simple dashboard focusing on model performance**:

```json
{
  "dashboard": {
    "title": "RAG System - Model Performance",
    "tags": ["models", "rag", "voice"],
    "timezone": "browser",
    "schemaVersion": 39,
    "panels": [
      {
        "id": 1,
        "title": "Model Inference Latency (p50/p95)",
        "type": "timeseries",
        "targets": [
          {
            "expr": "histogram_quantile(0.50, rate(model_inference_duration_seconds_bucket[5m]))",
            "legendFormat": "{{model_type}} p50",
            "refId": "A"
          },
          {
            "expr": "histogram_quantile(0.95, rate(model_inference_duration_seconds_bucket[5m]))",
            "legendFormat": "{{model_type}} p95",
            "refId": "B"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "unit": "s",
            "color": {"mode": "palette-classic"}
          }
        },
        "gridPos": {"x": 0, "y": 0, "w": 12, "h": 8}
      },
      {
        "id": 2,
        "title": "Model Request Rate",
        "type": "timeseries",
        "targets": [
          {
            "expr": "rate(model_inference_total[5m])",
            "legendFormat": "{{model_type}} - {{status}}",
            "refId": "A"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "unit": "reqps",
            "color": {"mode": "palette-classic"}
          }
        },
        "gridPos": {"x": 12, "y": 0, "w": 12, "h": 8}
      },
      {
        "id": 3,
        "title": "GPU Memory Usage",
        "type": "timeseries",
        "targets": [
          {
            "expr": "gpu_memory_used_bytes / 1024 / 1024 / 1024",
            "legendFormat": "{{device}} - {{model_type}}",
            "refId": "A"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "unit": "decgbytes",
            "color": {"mode": "palette-classic"},
            "thresholds": {
              "mode": "absolute",
              "steps": [
                {"value": 0, "color": "green"},
                {"value": 8, "color": "yellow"},
                {"value": 10, "color": "red"}
              ]
            }
          }
        },
        "gridPos": {"x": 0, "y": 8, "w": 12, "h": 6}
      },
      {
        "id": 4,
        "title": "Model Error Rate",
        "type": "timeseries",
        "targets": [
          {
            "expr": "rate(model_inference_total{status=\"error\"}[5m])",
            "legendFormat": "{{model_type}}",
            "refId": "A"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "unit": "reqps",
            "color": {"mode": "palette-classic"}
          }
        },
        "gridPos": {"x": 12, "y": 8, "w": 12, "h": 6}
      },
      {
        "id": 5,
        "title": "Voice Pipeline Latency Breakdown",
        "type": "timeseries",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(audio_rag_stage_duration_seconds_bucket[5m]))",
            "legendFormat": "{{stage}}",
            "refId": "A"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "unit": "s",
            "color": {"mode": "palette-classic"}
          }
        },
        "gridPos": {"x": 0, "y": 14, "w": 12, "h": 6}
      },
      {
        "id": 6,
        "title": "Voice Request Latency (End-to-End)",
        "type": "timeseries",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(voice_request_duration_seconds_bucket[5m]))",
            "legendFormat": "{{endpoint}}",
            "refId": "A"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "unit": "s",
            "color": {"mode": "palette-classic"}
          }
        },
        "gridPos": {"x": 12, "y": 14, "w": 12, "h": 6}
      },
      {
        "id": 7,
        "title": "Recent Error Logs (All Containers)",
        "type": "logs",
        "targets": [
          {
            "expr": "{job=\"docker_containers\"} |~ \"(?i)error|exception|failed\"",
            "refId": "A"
          }
        ],
        "options": {
          "showTime": true,
          "wrapLogMessage": true,
          "enableLogDetails": true,
          "sortOrder": "Descending"
        },
        "gridPos": {"x": 0, "y": 20, "w": 24, "h": 8}
      }
    ],
    "time": {
      "from": "now-1h",
      "to": "now"
    },
    "refresh": "30s"
  }
}
```

**Import dashboard**:
```bash
# Copy file to dashboards directory
cp model_monitoring.json monitoring/grafana/dashboards/

# Restart Grafana to auto-import
docker compose restart grafana
```

---

### Step 7: Add Simple Alert Rule

**Files**: [`monitoring/prometheus/alerts.yml`]

**Update với 1 alert rule đơn giản**:

```yaml
groups:
  - name: mvp_alerts
    interval: 1m
    rules:
      - alert: HighModelInferenceLatency
        expr: |
          histogram_quantile(0.95, 
            rate(model_inference_duration_seconds_bucket[5m])
          ) > 5
        for: 3m
        labels:
          severity: warning
        annotations:
          summary: "High model inference latency detected"
          description: "{{ $labels.model_type }} p95 latency is {{ $value | humanizeDuration }} (threshold: 5s)"
      
      - alert: HighVoiceErrorRate
        expr: |
          (
            rate(voice_request_errors_total[5m])
            /
            (rate(voice_request_duration_seconds_count[5m]) + 0.001)
          ) > 0.05
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "High error rate on voice endpoints"
          description: "{{ $labels.endpoint }} error rate is {{ $value | humanizePercentage }}"
```

**Reload Prometheus**:
```bash
curl -X POST http://localhost:9090/-/reload
```

---

### Step 8: Update tasks.md

**Files**: [`specs/001-improve-rag-system/tasks.md`]

**Update Phase 8 tasks**:

```markdown
## Phase 8: User Story 6 - Minimal MVP Monitoring (Priority: P6)

**Goal**: Essential observability với full model metrics (generation/embedding/rerank/guardrails) + voice pipeline monitoring

**Independent Test**: Trigger RAG + voice operations, verify all model metrics visible in Grafana

### Implementation for User Story 6 (MVP Scope)

**Infrastructure Setup**:
- [X] T111-T121 [US6] Basic monitoring stack configured (Prometheus, Loki, Tempo, Grafana)
- [ ] T122 [US6] Fix Prometheus config: Add GPU service scrape target in monitoring/prometheus/prometheus.yml
- [ ] T123 [US6] Fix Promtail config: Enable Docker auto-discovery in monitoring/promtail/promtail-config.yaml
- [ ] T124 [US6] Restart monitoring stack: `cd monitoring && docker compose restart prometheus promtail`

**GPU Service Instrumentation**:
- [ ] T125 [US6] Add prometheus-client to serving/qwen3_models/requirements.txt
- [ ] T126 [US6] Add /metrics endpoint in serving/qwen3_models/app.py (Prometheus exporter)
- [ ] T127 [US6] Instrument 4 model endpoints: /embed, /rerank, /guard, /stt với latency + count metrics
- [ ] T128 [US6] Add GPU memory tracking với background task (update every 30s)
- [ ] T129 [US6] Restart GPU service: `cd serving/qwen3_models && docker compose restart`

**Voice Pipeline Instrumentation**:
- [ ] T130 [US6] Add voice metrics in backend/src/core/metrics.py (3 metrics: duration, stage_duration, errors)
- [ ] T131 [US6] Instrument /v1/models/stt, /v1/models/tts, /v1/rag/audio in backend/src/routers/audio.py

**RAG Pipeline Tracing (Text + Audio)**:
- [ ] T132 [US6] Add detailed tracing to message_handler_task in backend/src/tasks.py (8 stages: query_enhancement, embedding_generation, vector_search, keyword_search, rrf_fusion, reranking, context_building, input_guardrails, generation, output_guardrails)
- [ ] T133 [US6] Add tracing to RAG router endpoint in backend/src/routers/rag.py (wraps Celery task)
- [ ] T134 [US6] Add detailed Audio RAG tracing in backend/src/routers/audio.py (4 stages: audio_upload, stt_transcribe, rag_processing, tts_synthesize) - reuses core RAG tracing
- [ ] T135 [US6] Restart backend: `cd backend && docker compose restart chatbot_api`

**Dashboards**:
- [ ] T136 [US6] Create dashboards provisioning config: monitoring/grafana/dashboards/dashboards.yaml
- [ ] T137 [US6] Download 3 templates: FastAPI #16110, Loki #13639, vLLM #23991
- [ ] T138 [US6] Build custom Model Monitoring dashboard: monitoring/grafana/dashboards/model_monitoring.json (7 panels)
- [ ] T139 [US6] Restart Grafana to import dashboards: `docker compose restart grafana`

**Alerts**:
- [ ] T140 [US6] Update monitoring/prometheus/alerts.yml với 2 rules (HighModelInferenceLatency, HighVoiceErrorRate)
- [ ] T141 [US6] Reload Prometheus: `curl -X POST http://localhost:9090/-/reload`

**Verification**:
- [ ] T142 [US6] Verify GPU metrics: `curl http://localhost:8002/metrics | grep model_inference`
- [ ] T143 [US6] Verify voice metrics: `curl http://localhost:8000/metrics | grep voice_`
- [ ] T144 [US6] Verify logs: Grafana Explore → Loki → `{job="docker_containers"}`
- [ ] T145 [US6] Verify RAG traces: Grafana Explore → Tempo → Service: chatbot_api → See 8-10 nested spans for text RAG
- [ ] T146 [US6] Verify Audio RAG traces: Search for audio_rag_query → See nested structure (audio_upload → stt → rag_pipeline with 8 sub-spans → tts)
- [ ] T147 [US6] Verify 4 dashboards: FastAPI, Loki, vLLM, Model Monitoring (all showing data)

**Git Example**: `git commit -m "Add minimal MVP monitoring with full model metrics + voice pipeline observability"`

**Checkpoint**: Essential monitoring operational, đủ visibility để debug model performance issues
```

---

## Verification Checklist

### Stack Health
- [ ] All monitoring services running: `docker ps | grep -E "prometheus|loki|tempo|grafana|promtail"`
- [ ] Prometheus targets UP: `curl http://localhost:9090/targets` (backend, vllm, gpu_service all UP)
- [ ] Promtail scraping containers: `docker logs promtail | grep "Starting Promtail"`

### Metrics
- [ ] Backend metrics: `curl http://localhost:8000/metrics | wc -l` (>50 lines)
- [ ] GPU service metrics: `curl http://localhost:8002/metrics | grep model_inference`
- [ ] Voice metrics: `curl http://localhost:8000/metrics | grep -E "voice_request|audio_rag_stage"`
- [ ] vLLM metrics: `curl http://vllm:8000/metrics` (if accessible)

### Logs
- [ ] Docker logs flowing to Loki: Grafana → Explore → Loki → `{job="docker_containers"}`
- [ ] Can filter by container: `{container="chatbot_api"}`
- [ ] Can filter by service: `{service="chatbot_api"}`
- [ ] Error logs visible: `{job="docker_containers"} |~ "(?i)error"`

### Dashboards
- [ ] 4 dashboards visible: Browse → Dashboards
  - FastAPI Template (imported)
  - Loki Logs Template (imported)
  - vLLM Template (imported)
  - Model Monitoring (custom)
- [ ] Model Monitoring dashboard shows data in all 7 panels
- [ ] No "No data" errors

### Tracing
- [ ] Audio RAG traces: Grafana → Explore → Tempo → Search traces → Service: chatbot_api
- [ ] Spans nested: audio_rag_query → stt → rag → tts
- [ ] Span attributes visible: audio_size_bytes, chunks_retrieved

### Alerts
- [ ] Alert rules loaded: `curl http://localhost:9090/api/v1/rules`
- [ ] No firing alerts initially

---

## What We're NOT Doing (MVP Scope)

### Skipped Features
1. **Infrastructure Exporters**: No Redis/ES/Node exporters - monitor manual khi issue
2. **JSON Logging**: Console logs đủ, Loki parses automatically
3. **Fine-grained Metrics**: No token/s, cache hit rates, batch sizes per model
4. **Multiple Specialized Dashboards**: 4 dashboards (3 templates + 1 custom) đủ
5. **Complex Alerts**: Chỉ 2 alerts (latency + errors)

### Why This Is OK for MVP
- **Focus on models**: Generation/embedding/rerank/guardrails metrics = 80% value
- **Logs cover infrastructure**: Container logs show Redis/ES issues
- **Templates save time**: Reuse community best practices
- **Iterate later**: Add complexity khi measured need arises

---

## Timeline Estimate

**Total**: ~9-11 hours implementation + 2 hours testing

- **Step 1** (Fix stack config): 1 hour
- **Step 2** (GPU service metrics): 2 hours (add endpoint + instrument 4 models)
- **Step 3** (Voice metrics): 1.5 hours (add metrics + instrument 3 endpoints)
- **Step 4** (RAG tracing): 2.5 hours (detailed tracing cho text RAG pipeline + audio RAG integration)
- **Step 5** (Import templates): 1 hour (download + configure)
- **Step 6** (Custom dashboard): 2 hours (build JSON + test 7 panels)
- **Step 7** (Alerts): 30 min
- **Step 8** (Update tasks): 30 min
- **Testing**: 2 hours (verify metrics, logs, traces, dashboards)

**~40% faster than comprehensive** (10h vs 16h) but keeps model visibility.

---

## Success Criteria

After implementation:

### Model Observability
- ✅ All 4 GPU models monitored: Embedding, Rerank, Guardrails, STT
- ✅ vLLM generation model monitored
- ✅ Latency p50/p95 visible per model
- ✅ Request rate + error rate per model
- ✅ GPU memory usage tracked

### Voice Pipeline
- ✅ End-to-end latency for STT/TTS/Audio RAG
- ✅ Stage-level breakdown (stt → rag → tts)
- ✅ Error tracking per endpoint
- ✅ Distributed tracing với 3 nested spans

### Logs & Traces
- ✅ All container logs searchable in Loki
- ✅ **Detailed RAG tracing** (Text): 8-10 nested spans per request
  - query_enhancement → embedding_generation → vector_search + keyword_search → rrf_fusion → reranking → context_building → input_guardrails → generation → output_guardrails
- ✅ **Audio RAG tracing**: 4 top-level spans + nested RAG spans
  - audio_upload → stt_transcribe → rag_processing (reuses 8 RAG spans) → tts_synthesize
- ✅ Can correlate logs ↔ traces ↔ metrics

### Dashboards
- ✅ 4 dashboards operational (3 templates + 1 custom)
- ✅ Model Monitoring dashboard shows:
  - Model latency comparison
  - Request rates
  - GPU memory
  - Error rates
  - Voice pipeline breakdown
  - Recent error logs

---

## Migration Path (MVP → Production)

**Week 1-2** (MVP): Implement minimal monitoring
- Focus: Model metrics + voice pipeline + basic logs/traces

**Week 3-4**: Add infrastructure exporters IF seeing issues
- Redis exporter → if cache issues
- ES exporter → if search performance issues
- Node exporter → if host resource issues

**Month 2**: Enhance dashboards
- Split Model Monitoring → separate dashboards per model type
- Add cache hit rate metrics
- Add token/s metrics for generation

**Month 3**: Advanced features
- JSON logging for structured parsing
- More detailed tracing (service-level)
- Alert tuning based on baseline data
- SLO/SLA tracking

---

## Comparison: Comprehensive vs Minimal

| Feature | Comprehensive | Minimal MVP | Difference |
|---------|--------------|-------------|------------|
| Infra exporters | 3 (Redis, ES, Node) | 0 | Skip for MVP |
| Dashboards | 7 (4 templates + 3 custom) | 4 (3 templates + 1 custom) | Focus models |
| Voice metrics | 5 detailed | 3 essential | Core only |
| GPU metrics | Full + batch tracking | Latency + memory | Enough |
| Tracing | All endpoints | **RAG pipeline detailed (text + audio)** | **Same depth** |
| Logging | JSON + files | Console | Simple |
| Alerts | 5 rules | 2 rules | Cover 80% |
| **Timeline** | **~16-20h** | **~11h** | **45% faster** |
| **Model visibility** | **Full** | **Full** | **Same** |
| **RAG tracing depth** | **Full** | **Full** | **Same** |

**Key insight**: Minimal version KEEPS full model observability (generation/embedding/rerank/guardrails) nhưng SKIPS infrastructure complexity.

---

## When to Upgrade

**Add infrastructure exporters when**:
- Seeing unexplained latency spikes → Check Redis/ES metrics
- Host resource alerts → Add Node exporter

**Add JSON logging when**:
- Need complex log parsing (extract structured fields)
- Need log-based metrics

**Add more tracing when**:
- Need to optimize specific service (instrument that service)
- Debugging complex multi-service flows

**Add more dashboards when**:
- Team >3 → Need role-specific views
- Multiple environments → Need per-env dashboards

**Rule of thumb**: MVP monitoring should answer "Is my model performing well?" và "What's slow/broken?". Add complexity khi cần answer more detailed questions.
