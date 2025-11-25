# Plan: Simplified Comprehensive Monitoring với Template Reuse & Docker Log Collection

Nâng cấp monitoring từ foundation hiện có lên full observability với approach đơn giản: reuse Grafana templates, collect logs từ tất cả containers, thêm basic metrics cho voice pipeline, và enhance tracing chỉ ở critical paths.

## Context

**Current State**:
- ✅ Monitoring stack deployed (Prometheus + Loki + Tempo + Grafana)
- ✅ Basic metrics exposed từ backend API (`/metrics` endpoint)
- ✅ OpenTelemetry tracing configured (OTLP → Tempo)
- ✅ Alerts defined nhưng chưa tune cho production
- ⚠️ Grafana dashboards = placeholder (empty panels)
- ⚠️ Logs chỉ output console (không write files)
- ❌ GPU service metrics không được scrape
- ❌ Infrastructure metrics (Redis, Elasticsearch, Node) missing
- ❌ Voice pipeline (STT/TTS/Audio RAG) chưa có dedicated monitoring

**Target State**:
- ✅ 4 production-ready dashboards (imported từ templates + 1 custom voice dashboard)
- ✅ Full log collection từ tất cả Docker containers
- ✅ Infrastructure metrics từ exporters (Redis, ES, Node)
- ✅ GPU service metrics exposed + scraped
- ✅ Voice pipeline monitoring với latency breakdown
- ✅ Critical path tracing (Audio RAG flow)
- ✅ Alert rules tuned với traffic thresholds

## Implementation Steps

### Step 1: Setup Infrastructure Exporters + Docker Log Collection

**Files**: [`monitoring/docker-compose.yml`], [`monitoring/prometheus/prometheus.yml`], [`monitoring/promtail/promtail-config.yaml`]

**Changes**:

1. **Add 3 exporters** vào `monitoring/docker-compose.yml`:
   ```yaml
   redis-exporter:
     image: oliver006/redis_exporter:v1.62.0
     container_name: redis_exporter
     environment:
       - REDIS_ADDR=redis://redis_db:6379
       - REDIS_PASSWORD=${REDIS_PASSWORD:-redisadmin}
     ports:
       - "9121:9121"
     networks:
       - medical_rag_network
   
   elasticsearch-exporter:
     image: quay.io/prometheuscommunity/elasticsearch-exporter:v1.7.0
     container_name: elasticsearch_exporter
     command:
       - '--es.uri=http://elasticsearch:9200'
       - '--es.all'
     ports:
       - "9114:9114"
     networks:
       - medical_rag_network
   
   node-exporter:
     image: prom/node-exporter:v1.8.2
     container_name: node_exporter
     command:
       - '--path.procfs=/host/proc'
       - '--path.sysfs=/host/sys'
       - '--collector.filesystem.mount-points-exclude=^/(sys|proc|dev|host|etc)($$|/)'
     volumes:
       - /proc:/host/proc:ro
       - /sys:/host/sys:ro
       - /:/rootfs:ro
     ports:
       - "9100:9100"
     networks:
       - medical_rag_network
   ```

2. **Mount Docker socket** cho Promtail trong `monitoring/docker-compose.yml`:
   ```yaml
   promtail:
     volumes:
       - ./promtail/promtail-config.yaml:/etc/promtail/config.yaml
       - /var/run/docker.sock:/var/run/docker.sock  # ADD THIS
       - /var/lib/docker/containers:/var/lib/docker/containers:ro
   ```

3. **Add scrape targets** vào `monitoring/prometheus/prometheus.yml`:
   ```yaml
   scrape_configs:
     # ... existing targets ...
     
     - job_name: 'redis'
       static_configs:
         - targets: ['redis_exporter:9121']
     
     - job_name: 'elasticsearch'
       static_configs:
         - targets: ['elasticsearch_exporter:9114']
     
     - job_name: 'node'
       static_configs:
         - targets: ['node_exporter:9100']
     
     - job_name: 'gpu_service'
       static_configs:
         - targets: ['extra_models_gpu:8002']
       metrics_path: '/metrics'
       scrape_interval: 30s  # Longer interval for GPU
   ```

4. **Update Promtail** để auto-discover Docker containers trong `monitoring/promtail/promtail-config.yaml`:
   ```yaml
   scrape_configs:
     # Keep existing backend job...
     
     # Enhanced Docker container logs
     - job_name: docker
       docker_sd_configs:
         - host: unix:///var/run/docker.sock
           refresh_interval: 5s
           filters:
             - name: label
               values: ["com.docker.compose.project=medical-rag"]  # Filter project
       relabel_configs:
         - source_labels: ['__meta_docker_container_name']
           regex: '/(.*)'
           target_label: 'container'
         - source_labels: ['__meta_docker_container_log_stream']
           target_label: 'stream'
         - source_labels: ['__meta_docker_container_label_com_docker_compose_service']
           target_label: 'service'
   ```

**Verification**:
```bash
cd monitoring
docker compose up -d
curl http://localhost:9121/metrics | head  # Redis metrics
curl http://localhost:9114/metrics | head  # ES metrics
curl http://localhost:9100/metrics | head  # Node metrics
```

---

### Step 2: Enable JSON Logging + File Output

**Files**: [`backend/src/configs/logging_config.py`], [`backend/docker-compose.yml`]

**Changes**:

1. **Uncomment file handler** trong `logging_config.py`:
   ```python
   def configure_logging(log_level: str = "INFO", json_logs: bool = False):
       logger.remove()
       
       # Determine JSON logs based on environment
       env = settings.environment or "development"
       use_json = json_logs or (env == "production")
       
       if use_json:
           # JSON format for production (Promtail parsing)
           logger.add(
               sys.stderr,
               format="{message}",
               level=log_level,
               serialize=True,
               backtrace=True,
               diagnose=True,
           )
           
           # UNCOMMENT THIS:
           logger.add(
               "/var/log/backend/app.log",
               format="{message}",
               level=log_level,
               serialize=True,
               rotation="100 MB",
               retention="30 days",
               compression="zip",
               backtrace=True,
               diagnose=True,
           )
       else:
           # Colorized format for development
           logger.add(sys.stderr, ...)
   
   configure_logging(
       log_level=settings.log_level or "INFO",
       json_logs=settings.environment == "production",
   )
   ```

2. **Add log volume** vào `backend/docker-compose.yml`:
   ```yaml
   chatbot_api:
     volumes:
       - backend_logs:/var/log/backend  # ADD THIS
       - nltk_data:/app/nltk_data
       - # ... other volumes
   
   volumes:
     backend_logs:  # ADD THIS
     qdrant_data:
     # ... other volumes
   ```

3. **Add JSON pipeline** vào `monitoring/promtail/promtail-config.yaml`:
   ```yaml
   scrape_configs:
     - job_name: backend
       static_configs:
         - targets:
             - localhost
           labels:
             job: backend
             __path__: /var/log/backend/*.log
       pipeline_stages:
         - json:
             expressions:
               timestamp: time
               level: level
               message: message
               function: function
               line: line
         - labels:
             level:
             function:
   ```

**Verification**:
```bash
docker exec chatbot_api ls -lh /var/log/backend/app.log
docker logs -f promtail | grep backend  # Check scraping
```

---

### Step 3: Import Grafana Dashboard Templates

**Files**: [`monitoring/grafana/dashboards/`]

**Changes**:

1. **Create provisioning config** `monitoring/grafana/dashboards/dashboards.yaml`:
   ```yaml
   apiVersion: 1
   
   providers:
     - name: 'default'
       orgId: 1
       folder: ''
       type: file
       disableDeletion: false
       updateIntervalSeconds: 10
       allowUiUpdates: true
       options:
         path: /etc/grafana/provisioning/dashboards
         foldersFromFilesStructure: true
   ```

2. **Download 4 templates** từ Grafana.com:
   ```bash
   cd monitoring/grafana/dashboards/
   
   # FastAPI Dashboard #16110
   curl -o fastapi_dashboard.json \
     "https://grafana.com/api/dashboards/16110/revisions/1/download"
   
   # Node Exporter Full #1860
   curl -o node_exporter_dashboard.json \
     "https://grafana.com/api/dashboards/1860/revisions/37/download"
   
   # Loki Dashboard #13639
   curl -o loki_logs_dashboard.json \
     "https://grafana.com/api/dashboards/13639/revisions/2/download"
   
   # vLLM Monitoring #23991
   curl -o vllm_dashboard.json \
     "https://grafana.com/api/dashboards/23991/revisions/1/download"
   ```

3. **Customize datasource variables** trong mỗi JSON (find/replace):
   ```bash
   # Replace datasource UIDs with our names
   sed -i 's/"uid": ".*"/"uid": "Prometheus"/g' *.json
   sed -i 's/"datasource": ".*Prometheus.*"/"datasource": "Prometheus"/g' *.json
   sed -i 's/"datasource": ".*Loki.*"/"datasource": "Loki"/g' *.json
   ```

4. **Update provisioning** trong `monitoring/docker-compose.yml`:
   ```yaml
   grafana:
     volumes:
       - ./grafana/dashboards:/etc/grafana/provisioning/dashboards
       - ./grafana/datasources.yaml:/etc/grafana/provisioning/datasources/datasources.yaml
       # Dashboards will be auto-imported from dashboards/ directory
   ```

**Verification**:
```bash
docker compose restart grafana
# Open http://localhost:3000
# Check Dashboards → Browse → Should see 4 imported dashboards
```

---

### Step 4: Build Custom Voice Processing Dashboard

**Files**: [`monitoring/grafana/dashboards/voice_processing.json`]

**Changes**:

Create new dashboard JSON với 6 panels:

```json
{
  "dashboard": {
    "title": "Voice Processing Pipeline",
    "tags": ["voice", "stt", "tts", "audio-rag"],
    "timezone": "browser",
    "panels": [
      {
        "id": 1,
        "title": "Voice Request Rate",
        "type": "timeseries",
        "targets": [
          {
            "expr": "rate(model_inference_duration_seconds_count{model_type=~\"stt|tts\"}[5m])",
            "legendFormat": "{{model_type}}"
          }
        ],
        "gridPos": {"x": 0, "y": 0, "w": 12, "h": 8}
      },
      {
        "id": 2,
        "title": "Audio RAG Latency Heatmap",
        "type": "heatmap",
        "targets": [
          {
            "expr": "rate(audio_rag_stage_duration_seconds_bucket[5m])",
            "legendFormat": "{{stage}}"
          }
        ],
        "gridPos": {"x": 12, "y": 0, "w": 12, "h": 8}
      },
      {
        "id": 3,
        "title": "Cache Hit Rate (STT/TTS)",
        "type": "gauge",
        "targets": [
          {
            "expr": "voice_cache_effectiveness",
            "legendFormat": "{{cache_type}}"
          }
        ],
        "gridPos": {"x": 0, "y": 8, "w": 8, "h": 6}
      },
      {
        "id": 4,
        "title": "Error Rate by Endpoint",
        "type": "timeseries",
        "targets": [
          {
            "expr": "rate(http_requests_total{path=~\"/v1/models/(stt|tts)|/v1/rag/audio\", status=~\"5..\"}[5m])",
            "legendFormat": "{{path}}"
          }
        ],
        "gridPos": {"x": 8, "y": 8, "w": 8, "h": 6}
      },
      {
        "id": 5,
        "title": "Audio File Size Distribution",
        "type": "histogram",
        "targets": [
          {
            "expr": "audio_file_size_bytes_bucket",
            "legendFormat": "{{le}}"
          }
        ],
        "gridPos": {"x": 16, "y": 8, "w": 8, "h": 6}
      },
      {
        "id": 6,
        "title": "Voice Pipeline Logs",
        "type": "logs",
        "targets": [
          {
            "expr": "{container=\"chatbot_api\"} |= \"stt\" or \"tts\" or \"audio\"",
            "refId": "A",
            "datasource": "Loki"
          }
        ],
        "options": {
          "showTime": true,
          "wrapLogMessage": true,
          "enableLogDetails": true
        },
        "gridPos": {"x": 0, "y": 14, "w": 24, "h": 8}
      }
    ],
    "templating": {
      "list": [
        {
          "name": "datasource",
          "type": "datasource",
          "query": "prometheus"
        }
      ]
    },
    "time": {
      "from": "now-6h",
      "to": "now"
    },
    "refresh": "10s"
  }
}
```

**Add drill-down links** (data links trong panel config):
- Click vào error spike → Navigate sang Explore view với filtered logs
- Click vào latency spike → Show trace view với `trace_id`

**Verification**:
```bash
# Import dashboard
curl -X POST http://localhost:3000/api/dashboards/db \
  -H "Content-Type: application/json" \
  -d @monitoring/grafana/dashboards/voice_processing.json
```

---

### Step 5: Add Voice Metrics

**Files**: [`backend/src/core/metrics.py`], [`backend/src/routers/audio.py`]

**Changes**:

1. **Define metrics** trong `metrics.py`:
   ```python
   from prometheus_client import Counter, Histogram, Gauge
   
   # ... existing metrics ...
   
   # Voice processing metrics
   audio_file_size_bytes = Histogram(
       "audio_file_size_bytes",
       "Audio file size in bytes",
       ["endpoint"],
       buckets=[10_000, 100_000, 1_000_000, 10_000_000],  # 10KB, 100KB, 1MB, 10MB
   )
   
   voice_cache_effectiveness = Gauge(
       "voice_cache_effectiveness",
       "Cache hit rate for voice services",
       ["cache_type"],  # stt, tts
   )
   
   audio_rag_stage_duration_seconds = Histogram(
       "audio_rag_stage_duration_seconds",
       "Duration of each Audio RAG pipeline stage",
       ["stage"],  # stt, retrieval, generation, tts
       buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0],
   )
   ```

2. **Instrument endpoints** trong `audio.py`:
   ```python
   from ..core.metrics import (
       audio_file_size_bytes,
       voice_cache_effectiveness,
       audio_rag_stage_duration_seconds,
   )
   
   @router.post("/v1/models/stt")
   async def speech_to_text(file: UploadFile):
       # Record file size
       audio_bytes = await file.read()
       audio_file_size_bytes.labels(endpoint="stt").observe(len(audio_bytes))
       
       # ... existing code ...
       
       # Update cache effectiveness (calculate from service)
       cache_hit_rate = stt_service.get_cache_hit_rate()  # Need to implement
       voice_cache_effectiveness.labels(cache_type="stt").set(cache_hit_rate)
   
   @router.post("/v1/rag/audio")
   async def audio_rag_query(file: UploadFile):
       audio_bytes = await file.read()
       audio_file_size_bytes.labels(endpoint="audio_rag").observe(len(audio_bytes))
       
       # Track each stage
       start = time.time()
       transcript = await stt_service.transcribe(audio_bytes)
       audio_rag_stage_duration_seconds.labels(stage="stt").observe(time.time() - start)
       
       start = time.time()
       rag_result = await rag_query(transcript)
       audio_rag_stage_duration_seconds.labels(stage="rag").observe(time.time() - start)
       
       start = time.time()
       audio = await tts_service.synthesize(rag_result)
       audio_rag_stage_duration_seconds.labels(stage="tts").observe(time.time() - start)
       
       return audio
   ```

3. **Add cache hit rate tracking** trong `stt_service.py` và `tts_service.py`:
   ```python
   class STTService:
       def __init__(self):
           self._cache_hits = 0
           self._cache_misses = 0
       
       async def transcribe(self, audio: bytes) -> str:
           cache_key = self._get_cache_key(audio)
           cached = await redis.get(cache_key)
           
           if cached:
               self._cache_hits += 1
               return cached
           
           self._cache_misses += 1
           result = await self._transcribe_remote(audio)
           await redis.set(cache_key, result, ex=3600)
           return result
       
       def get_cache_hit_rate(self) -> float:
           total = self._cache_hits + self._cache_misses
           return self._cache_hits / total if total > 0 else 0.0
   ```

**Verification**:
```bash
curl -X POST http://localhost:8000/v1/models/stt -F "file=@test.wav"
curl http://localhost:8000/metrics | grep audio_
```

---

### Step 6: Add GPU Service Metrics

**Files**: [`serving/qwen3_models/app.py`]

**Changes**:

1. **Install instrumentator**:
   ```bash
   # In serving/qwen3_models/requirements.txt
   prometheus-fastapi-instrumentator==7.0.0
   ```

2. **Add metrics endpoint** trong `app.py`:
   ```python
   from fastapi import FastAPI
   from prometheus_client import Gauge, Histogram, make_asgi_app
   from prometheus_fastapi_instrumentator import Instrumentator
   import torch
   
   app = FastAPI()
   
   # Auto-instrument HTTP metrics
   Instrumentator().instrument(app).expose(app)
   
   # Custom GPU metrics
   gpu_memory_used_bytes = Gauge(
       "gpu_memory_used_bytes",
       "GPU memory allocated in bytes",
       ["device"]
   )
   
   model_batch_size = Histogram(
       "model_batch_size",
       "Batch size for model inference",
       ["model_type"],
       buckets=[1, 2, 4, 8, 16, 32, 64],
   )
   
   @app.on_event("startup")
   async def update_gpu_metrics():
       """Background task to update GPU metrics every 30s"""
       import asyncio
       while True:
           if torch.cuda.is_available():
               for i in range(torch.cuda.device_count()):
                   memory = torch.cuda.memory_allocated(i)
                   gpu_memory_used_bytes.labels(device=f"cuda:{i}").set(memory)
           await asyncio.sleep(30)
   
   @app.post("/embed")
   async def embed_texts(texts: list[str]):
       model_batch_size.labels(model_type="embedding").observe(len(texts))
       # ... existing code ...
   
   @app.post("/rerank")
   async def rerank_texts(query: str, texts: list[str]):
       model_batch_size.labels(model_type="rerank").observe(len(texts))
       # ... existing code ...
   ```

3. **Add health check** (if not exists):
   ```python
   @app.get("/health")
   async def health_check():
       return {
           "status": "healthy",
           "gpu_available": torch.cuda.is_available(),
           "gpu_count": torch.cuda.device_count() if torch.cuda.is_available() else 0,
       }
   ```

**Verification**:
```bash
curl http://localhost:8002/metrics | grep gpu_
curl http://localhost:8002/health
```

---

### Step 7: Add Critical Path Tracing

**Files**: [`backend/src/routers/audio.py`]

**Changes**:

1. **Instrument Audio RAG endpoint** với nested spans:
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
       with tracer.start_as_current_span("audio_rag_query") as span:
           # Set top-level attributes
           span.set_attribute("user_identifier", user_identifier)
           span.set_attribute("thread_id", thread_id)
           
           try:
               # Stage 1: Upload
               with tracer.start_as_current_span("audio_upload") as upload_span:
                   audio_bytes = await file.read()
                   upload_span.set_attribute("audio_size_bytes", len(audio_bytes))
                   audio_file_size_bytes.labels(endpoint="audio_rag").observe(len(audio_bytes))
               
               # Stage 2: STT
               with tracer.start_as_current_span("stt_transcribe") as stt_span:
                   transcript = await stt_service.transcribe(audio_bytes)
                   stt_span.set_attribute("transcript_length", len(transcript))
                   stt_span.set_attribute("cache_hit", transcript in cache)  # Implement check
               
               # Stage 3: RAG Query
               with tracer.start_as_current_span("rag_query") as rag_span:
                   rag_result = await rag_service.query(
                       user_identifier=user_identifier,
                       thread_id=thread_id,
                       query=transcript,
                   )
                   rag_span.set_attribute("response_length", len(rag_result.answer))
                   rag_span.set_attribute("chunk_count", len(rag_result.chunks))
               
               # Stage 4: TTS
               with tracer.start_as_current_span("tts_synthesize") as tts_span:
                   audio_path = await tts_service.synthesize(rag_result.answer)
                   tts_span.set_attribute("audio_path", audio_path)
                   tts_span.set_attribute("cache_hit", audio_path in cache)
               
               span.set_status(Status(StatusCode.OK))
               return FileResponse(audio_path)
               
           except Exception as e:
               span.set_status(Status(StatusCode.ERROR, str(e)))
               span.record_exception(e)
               raise
   ```

2. **Propagate trace_id** qua Redis cache keys:
   ```python
   from opentelemetry import trace
   
   def get_cache_key(audio_hash: str) -> str:
       ctx = trace.get_current_span().get_span_context()
       trace_id = format(ctx.trace_id, '032x') if ctx.is_valid else 'notrace'
       return f"stt:{audio_hash}:{trace_id}"
   ```

**Verification**:
```bash
# Make request
curl -X POST http://localhost:8000/v1/rag/audio \
  -F "file=@test.wav" \
  -F "user_identifier=test_user" \
  -F "thread_id=thread_123"

# Check Tempo via Grafana Explore
# Query: {service_name="chatbot_api"} | trace_id="..."
```

---

### Step 8: Update tasks.md

**Files**: [`specs/001-improve-rag-system/tasks.md`]

**Changes**:

Update Phase 8 tasks with completion status và specific details:

```markdown
## Phase 8: User Story 6 - Comprehensive System Monitoring (Priority: P6)

**Goal**: System exposes detailed metrics, logs, and traces for RAG pipeline observability and debugging

**Independent Test**: Trigger RAG operations and verify metrics are collected, logs are written, and traces are captured

### Implementation for User Story 6

- [X] T111 [P] [US6] Create monitoring/prometheus/alerts.yml with alerting rules for high error rates, high latency
- [X] T112 [P] [US6] Create monitoring/grafana/dashboards/rag_pipeline.json with RAG-specific metrics visualization
- [X] T113 [P] [US6] Create monitoring/grafana/dashboards/model_serving.json with vLLM and FastAPI metrics
- [X] T114 [P] [US6] Create monitoring/grafana/dashboards/system_health.json with CPU, memory, GPU utilization
- [X] T115 [P] [US6] Create monitoring/grafana/datasources.yaml to connect Prometheus, Loki, and Tempo
- [X] T116 [US6] Add structured logging to all RAG pipeline stages in backend/src/tasks.py (embedding, retrieval, reranking, generation)
- [X] T117 [P] [US6] Configure Promtail in monitoring/promtail/promtail-config.yaml to scrape backend logs
- [X] T118 [P] [US6] Add trace spans to RAG pipeline in backend/src/tasks.py using OpenTelemetry decorators
- [X] T119 [US6] Configure Tempo exporter in backend/src/main.py to send traces to Tempo instance
- [X] T120 [P] [US6] Add model serving health check endpoint in backend/src/main.py: GET /health/models
- [X] T121 [P] [US6] Expose Prometheus metrics endpoint in backend/src/main.py: GET /metrics
- [ ] T122 [US6] Deploy monitoring stack: `cd monitoring && docker compose up -d`
- [ ] T123 [US6] Import Grafana dashboards: Download templates from Grafana.com (#16110, #1860, #13639, #23991)
- [ ] T124 [US6] Verify metrics flowing: `curl http://localhost:9090/targets` (all targets UP)
- [ ] T125 [US6] Verify logs captured: Grafana Explore → Loki → `{container="chatbot_api"}`
- [ ] T126 [US6] Verify traces: Grafana Explore → Tempo → Search by `service_name="chatbot_api"`

**New Tasks - Voice Monitoring**:

- [ ] T127 [P] [US6] Add infrastructure exporters to monitoring/docker-compose.yml (redis-exporter, elasticsearch-exporter, node-exporter)
- [ ] T128 [P] [US6] Enable JSON logging + file output in backend/src/configs/logging_config.py (production mode)
- [ ] T129 [P] [US6] Create voice processing dashboard in monitoring/grafana/dashboards/voice_processing.json
- [ ] T130 [P] [US6] Add GPU service metrics endpoint in serving/qwen3_models/app.py: GET /metrics
- [ ] T131 [US6] Add voice pipeline tracing in backend/src/routers/audio.py (STT → RAG → TTS spans)
- [ ] T132 [US6] Update alert rules in monitoring/prometheus/alerts.yml with voice-specific alerts (STT timeout, TTS errors)
- [ ] T133 [US6] Add scrape target for GPU service in monitoring/prometheus/prometheus.yml: extra_models_gpu:8002
- [ ] T134 [US6] Configure dashboard drill-down links (error panel → Loki logs, latency spike → Tempo traces)
- [ ] T135 [US6] Verify voice metrics: `curl http://localhost:8000/metrics | grep audio_`

**Git Example**: `git commit -m "Deploy full observability stack with voice processing monitoring"`

**Checkpoint**: At this point, comprehensive monitoring is operational with dashboards showing system health + voice pipeline metrics
```

---

## Verification Checklist

### Infrastructure
- [ ] All exporters running: `docker ps | grep exporter`
- [ ] Prometheus scraping all targets: `curl http://localhost:9090/targets`
- [ ] Loki receiving logs: `curl http://localhost:3100/ready`
- [ ] Tempo receiving traces: `curl http://localhost:3200/status`

### Metrics
- [ ] Backend metrics: `curl http://localhost:8000/metrics | wc -l` (>100 lines)
- [ ] GPU metrics: `curl http://localhost:8002/metrics | grep gpu_`
- [ ] Voice metrics: `curl http://localhost:8000/metrics | grep audio_`
- [ ] Redis metrics: `curl http://localhost:9121/metrics | grep redis_`

### Logs
- [ ] Backend logs writing to file: `docker exec chatbot_api ls /var/log/backend/`
- [ ] Promtail scraping: `docker logs promtail | grep "Clients configured"`
- [ ] JSON logs parseable: `cat backend_logs/app.log | jq .`

### Dashboards
- [ ] 7 dashboards visible in Grafana: Browse → Dashboards
  - FastAPI (imported)
  - Node Exporter (imported)
  - Loki Logs (imported)
  - vLLM (imported)
  - System Health (placeholder → to be built)
  - RAG Pipeline (placeholder → to be built)
  - Model Serving (placeholder → to be built)
  - Voice Processing (custom built)

### Tracing
- [ ] Audio RAG traces visible: Grafana Explore → Tempo → Search service_name="chatbot_api"
- [ ] Spans nested correctly: audio_rag_query → stt_transcribe → rag_query → tts_synthesize
- [ ] Trace attributes present: audio_size_bytes, transcript_length, cache_hit

### Alerts
- [ ] Alert rules loaded: `curl http://localhost:9090/api/v1/rules`
- [ ] No firing alerts (initially): `curl http://localhost:9090/api/v1/alerts`

---

## Performance Impact Assessment

**Estimated Overhead**:
- Prometheus scraping: <1% CPU (30s interval)
- Loki log shipping: ~50MB/day logs → <5MB/day compressed
- Tempo tracing: <2% latency overhead (batch processing)
- JSON logging: +10-15% log size vs text format
- GPU metrics: <0.1% inference overhead (30s interval, cached reads)

**Mitigation**:
- Sampling: 10% traces in production (config via `OTEL_TRACES_SAMPLER_ARG=0.1`)
- Log retention: 30 days (auto-cleanup)
- Metrics retention: 30 days (configurable in Prometheus)
- Dashboard refresh: 10s default (adjustable per panel)

---

## Further Considerations

### 1. Dashboard Template Customization
**Question**: Import nguyên bản hay customize labels/queries?

**Recommendation**: 
- Import template → Save as copy → Customize minimal (datasource, panel titles)
- Keep queries gốc để tận dụng best practices
- Save customized version với suffix `_custom.json`
- Version control cả original + custom trong Git

**Reasoning**: Templates đã được community test kỹ, chỉ customize khi cần thiết

---

### 2. Log Collection Overhead
**Question**: Docker logs qua Promtail có impact performance?

**Recommendation**:
- Config Promtail với rate limit: `rate_limit_mb: 50`
- Filter containers by label: `logging=enabled` (add to compose files)
- Max streams: `max_streams: 5000`
- Chỉ scrape containers cần debug (exclude Redis, Postgres internal logs)

**Reasoning**: Production logs có thể spike cao, cần rate limiting

---

### 3. GPU Metrics Collection Frequency
**Question**: Scrape GPU mỗi 10s có ảnh hưởng inference?

**Recommendation**:
- Tăng interval lên 30s cho GPU service
- Metrics đọc từ PyTorch cache (`torch.cuda.memory_allocated()`) - no CUDA API calls
- Async background task update metrics (không block requests)
- Monitor scrape duration: nếu >1s thì tăng interval lên 60s

**Reasoning**: GPU metrics ít thay đổi nhanh, không cần real-time

---

### 4. Voice Dashboard Drill-Down Strategy
**Question**: Link từ overview dashboard vào detailed logs như thế nào?

**Recommendation**:
- Dùng Grafana data links với variable `${__data.fields.trace_id}`
- Click panel → Navigate sang Explore với Loki query:
  ```
  {container="chatbot_api"} | json | trace_id="${__data.fields.trace_id}"
  ```
- Add URL params: `&var-trace_id=${__data.fields.trace_id}`
- Configure trong panel options → Data links → Title="View Logs" URL="/explore?..."

**Reasoning**: Native Grafana feature, không cần custom code

---

### 5. Alert Rules for Voice Pipeline
**Question**: Alert khi nào? STT timeout? TTS API quota?

**Recommendation**:
Add 3 alerts trong `monitoring/prometheus/alerts.yml`:

```yaml
groups:
  - name: voice_processing
    interval: 30s
    rules:
      - alert: HighVoiceErrorRate
        expr: rate(http_requests_total{path=~"/v1/models/(stt|tts)|/v1/rag/audio", status=~"5.."}[5m]) > 0.05
        for: 2m
        annotations:
          summary: "High error rate on voice endpoints"
          description: "Voice endpoints seeing {{ $value }} errors/sec"
      
      - alert: STTTimeout
        expr: histogram_quantile(0.95, rate(audio_rag_stage_duration_seconds_bucket{stage="stt"}[5m])) > 10
        for: 5m
        annotations:
          summary: "STT processing is slow"
          description: "95th percentile STT latency is {{ $value }}s"
      
      - alert: LowVoiceCacheHitRate
        expr: voice_cache_effectiveness < 0.2
        for: 10m
        annotations:
          summary: "Voice cache hit rate is low"
          description: "Cache hit rate for {{ $labels.cache_type }} is {{ $value }}"
```

**Reasoning**: Focus on user-impacting issues (errors, timeouts, poor cache performance)

---

## Success Metrics

After implementation, verify:

1. **Observability Coverage**: 
   - ✅ 100% requests traced (sampling in production)
   - ✅ All containers logging to Loki
   - ✅ All services exposing metrics

2. **Dashboard Completeness**:
   - ✅ 7 dashboards operational
   - ✅ All panels showing data (no "No data" states)
   - ✅ Drill-down links working

3. **Performance**:
   - ✅ Monitoring overhead <5% total latency
   - ✅ Log shipping lag <10s
   - ✅ Trace completion rate >95%

4. **Alerts**:
   - ✅ No false positive alerts for 24h
   - ✅ Alert fires within 2 minutes of issue
   - ✅ Runbook links working

---

## Timeline Estimate

**Total**: ~12-16 hours implementation + 4 hours testing/tuning

- **Step 1** (Exporters + Docker logs): 2 hours
- **Step 2** (JSON logging): 1 hour
- **Step 3** (Import templates): 2 hours (download + customize)
- **Step 4** (Voice dashboard): 3 hours (build JSON + test)
- **Step 5** (Voice metrics): 2 hours
- **Step 6** (GPU metrics): 2 hours
- **Step 7** (Tracing): 2 hours
- **Step 8** (Update tasks): 1 hour
- **Testing + Tuning**: 4 hours (alert thresholds, dashboard layout, drill-downs)

---

## Next Steps After Implementation

1. **Load Testing Integration**: Run Locust tests from Phase 7, observe metrics under load
2. **Alert Tuning**: Adjust thresholds based on 7-day baseline data
3. **Dashboard Refinement**: Add more drill-downs based on debugging patterns
4. **Documentation**: Create runbook for common alerts (what to check, how to mitigate)
5. **Team Training**: Walk team through dashboards, show how to debug using traces
