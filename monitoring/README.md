# Monitoring System - Setup & Troubleshooting

## Fixed Issues (2025-11-25)

### 1. FastAPI Metrics Not Showing
**Problem**: Prometheus không thể scrape metrics từ FastAPI backend.
**Root Cause**: Metrics endpoint có trailing slash (`/metrics/`) nhưng Prometheus config chỉ định `/metrics`.
**Solution**: Updated Prometheus config to use `/metrics/` path.

```yaml
# monitoring/prometheus/prometheus.yml
- job_name: 'backend'
  metrics_path: '/metrics/'  # Added trailing slash
```

### 2. vLLM Metrics Not Showing
**Problem**: Grafana dashboard chỉ hiển thị 4 models (embedding, rerank, guardrails, stt) thay vì 5 (thêm generation model từ vLLM).
**Root Cause**:
- vLLM remote server có Basic Authentication (401 Unauthorized)
- Prometheus config không có credentials để scrape metrics

**Solution**:
1. Added basic_auth configuration cho vLLM job
2. Cần thêm env vars vào monitoring stack

```yaml
# monitoring/prometheus/prometheus.yml
- job_name: 'vllm'
  basic_auth:
    username: ${VLLM_BASIC_AUTH_USERNAME}
    password: ${VLLM_BASIC_AUTH_PASSWORD}
```

**Required Environment Variables**:
```bash
# monitoring/.env (create this file)
VLLM_BASIC_AUTH_USERNAME=your_username
VLLM_BASIC_AUTH_PASSWORD=your_password
```

**Update docker-compose.yml**:
```yaml
# monitoring/docker-compose.yml
services:
  prometheus:
    env_file:
      - .env  # Add this line
    environment:
      - VLLM_BASIC_AUTH_USERNAME=${VLLM_BASIC_AUTH_USERNAME}
      - VLLM_BASIC_AUTH_PASSWORD=${VLLM_BASIC_AUTH_PASSWORD}
```

### 3. Tempo Tracing Not Working
**Problem**: Không thể trace requests qua Tempo.
**Root Cause**:
- `tempo_endpoint` không được define trong backend settings
- Hardcoded fallback không được sử dụng đúng cách

**Solution**:
1. Added `tempo_endpoint` và `tempo_enabled` config trong backend settings
2. Improved error handling và logging
3. Added toggle để disable tracing khi cần

```python
# backend/src/configs/setup.py
tempo_endpoint: str = Field(default=os.getenv("TEMPO_ENDPOINT", "http://tempo:4317"))
tempo_enabled: bool = Field(default=os.getenv("TEMPO_ENABLED", "true").lower() == "true")
```

**Environment Variables** (backend/.env):
```bash
TEMPO_ENDPOINT=http://tempo:4317
TEMPO_ENABLED=true
```

## Quick Start

### 1. Setup Environment Variables

**Backend** (backend/.env):
```bash
# Monitoring
TEMPO_ENDPOINT=http://tempo:4317
TEMPO_ENABLED=true
```

**Monitoring Stack** (monitoring/.env):
```bash
# vLLM Metrics Authentication
VLLM_BASIC_AUTH_USERNAME=your_username
VLLM_BASIC_AUTH_PASSWORD=your_password

# Grafana
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=admin
```

### 2. Start Monitoring Stack

```bash
cd monitoring
docker compose up -d
```

### 3. Restart Backend (to apply new config)

```bash
cd backend
docker compose restart chatbot_api
```

### 4. Verify Metrics

**Backend metrics**:
```bash
curl http://localhost:8000/metrics/ | head -50
```

**GPU service metrics**:
```bash
curl http://localhost:8002/metrics | head -50
```

**vLLM metrics** (requires auth):
```bash
curl -u username:password http://171.248.40.12:44624/metrics | head -50
```

### 5. Access Dashboards

- **Grafana**: http://localhost:3000 (admin/admin)
- **Prometheus**: http://localhost:9090
- **Tempo**: http://localhost:3200

## LangSmith Alternative (Recommended for LLM Tracing)

### Why LangSmith?

**Problems with Tempo for LLM tracing**:
- Generic tracing tool (không optimize cho LLM pipelines)
- Complex setup với OpenTelemetry instrumentation
- Không có built-in support cho prompt/completion tracking
- Khó debug RAG pipeline (retrieval → rerank → generation flow)
- Không có evaluation metrics (faithfulness, relevance, etc.)

**Benefits of LangSmith**:
- **Native LLM support**: Automatically tracks prompts, completions, tokens, latency
- **RAG-specific features**: Retrieval tracing, reranking scores, context tracking
- **Built-in evaluators**: Faithfulness, answer relevance, hallucination detection
- **Better UI**: Prompt/completion diff, conversation threads, error debugging
- **Easy integration**: Single SDK (LangChain/LangGraph compatible)
- **No infrastructure**: Cloud-based (no need to run Tempo/Loki/Grafana)

### Migration to LangSmith

**1. Install LangSmith SDK**:
```bash
cd backend
uv add langsmith
```

**2. Configure environment** (backend/.env):
```bash
# LangSmith
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your_api_key
LANGCHAIN_PROJECT=vietnamese-medical-rag

# Disable Tempo (optional)
TEMPO_ENABLED=false
```

**3. Update RAG service** (backend/src/services/rag_service.py):
```python
from langsmith import traceable

@traceable(name="rag_query", run_type="chain")
def rag_query(query: str, bot_id: str):
    # Your RAG logic here
    return result
```

**4. Track individual stages**:
```python
from langsmith import traceable

@traceable(name="vector_search", run_type="retriever")
def vector_search(query_embedding, top_k):
    # Vector search logic
    return results

@traceable(name="rerank", run_type="reranker")
def rerank(query, documents):
    # Reranking logic
    return ranked_docs

@traceable(name="generate_response", run_type="llm")
def generate_response(prompt, context):
    # Generation logic
    return response
```

**Benefits over current Tempo setup**:
- Zero config (no Prometheus/Grafana/Tempo stack)
- Automatic prompt/completion logging
- Token usage tracking per request
- Cost estimation
- Evaluation datasets và automated testing
- Better error debugging (see exact prompt that failed)

### Hybrid Approach (Recommended)

**Use Tempo for**:
- Infrastructure metrics (FastAPI, Redis, Elasticsearch)
- System performance (CPU, memory, latency)
- General request tracing

**Use LangSmith for**:
- LLM-specific tracing (prompts, completions, tokens)
- RAG pipeline debugging (retrieval quality, reranking scores)
- Evaluation và testing
- Cost tracking

## Grafana Dashboards

### Available Dashboards

1. **FastAPI Backend** (`fastapi_template.json`)
   - Total requests
   - Request rate
   - Error rate
   - Request duration (p50, p95, p99)
   - RAG pipeline stages latency
   - Cache hit/miss rates

2. **vLLM Generation Model** (`vllm_template.json`)
   - Tokens per second (throughput)
   - Request queue length
   - Time to first token (TTFT)
   - Time per output token (TPOT)
   - GPU utilization
   - Model cache hit rate

3. **Model Monitoring** (`model_monitoring.json`)
   - Inference latency by model (embedding, rerank, guardrails, stt, generation)
   - Request count by model
   - Error rates by model
   - GPU memory usage

4. **HTTP Tracing** (`http_tracing.json`)
   - Request traces from Tempo
   - Distributed tracing visualization
   - Span duration analysis

## Troubleshooting

### Metrics not showing in Grafana

**Check Prometheus targets**:
```bash
# Go to http://localhost:9090/targets
# All targets should be "UP" (green)
```

**If backend target is DOWN**:
```bash
# Test metrics endpoint
curl http://localhost:8000/metrics/

# Check backend logs
docker logs chatbot_api --tail 50
```

**If vLLM target is DOWN**:
```bash
# Check credentials
curl -u username:password http://171.248.40.12:44624/metrics

# Verify prometheus env vars
docker exec prometheus env | grep VLLM
```

### Traces not showing in Tempo

**Check Tempo health**:
```bash
curl http://localhost:3200/ready
```

**Check backend logs for OpenTelemetry errors**:
```bash
docker logs chatbot_api | grep -i "opentelemetry\|tempo\|tracing"
```

**Verify OTLP endpoint is reachable**:
```bash
# From backend container
docker exec chatbot_api nc -zv tempo 4317
```

### Grafana dashboard shows "No data"

**Check datasource configuration**:
1. Go to Grafana → Configuration → Data Sources
2. Test Prometheus connection (should be green)
3. Test Tempo connection (should be green)

**Check metric names**:
```bash
# List all available metrics
curl http://localhost:9090/api/v1/label/__name__/values
```

**Re-import dashboard**:
1. Go to Grafana → Dashboards → New → Import
2. Upload JSON file from `monitoring/grafana/dashboards/`

## Metrics Reference

### Backend Metrics (FastAPI)

```prometheus
# RAG pipeline
rag_requests_total{bot_id, status}
rag_request_duration_seconds{bot_id, stage}

# Cache
cache_hits_total{cache_type}
cache_misses_total{cache_type}

# Search
rag_search_requests_total{search_type}
rag_search_duration_seconds{search_type}

# Model inference
model_inference_duration_seconds{model_type, model_name}

# Voice processing
voice_request_duration_seconds{endpoint}
audio_rag_stage_duration_seconds{stage}
voice_request_errors_total{endpoint, error_type}
```

### vLLM Metrics

```prometheus
# Core metrics
vllm:num_requests_running
vllm:num_requests_waiting
vllm:gpu_cache_usage_perc
vllm:time_to_first_token_seconds
vllm:time_per_output_token_seconds

# Throughput
vllm:request_success_total
vllm:prompt_tokens_total
vllm:generation_tokens_total
```

### GPU Service Metrics

```prometheus
# GPU memory
gpu_memory_used_bytes{device, model_type}

# Model inference
model_inference_duration_seconds{model_type, model_name}
model_inference_total{model_type, model_name, status}
```

## Next Steps

1. **Add custom metrics** cho business logic (e.g., query categories, user satisfaction)
2. **Setup alerts** trong Prometheus (high error rate, slow response time)
3. **Implement LangSmith** cho LLM-specific tracing và evaluation
4. **Add logs aggregation** với Loki (structured logging từ backend)
5. **Setup SLO/SLI tracking** cho production readiness
