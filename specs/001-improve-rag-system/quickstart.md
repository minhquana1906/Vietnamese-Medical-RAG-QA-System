# Quickstart Guide

**Feature**: RAG System Comprehensive Improvements
**Branch**: `001-improve-rag-system`
**Date**: 2025-10-31

## Overview

This guide provides step-by-step instructions to set up the upgraded Vietnamese Medical RAG QA System with Chainlit UI, Qwen3 models, hybrid search, caching, and comprehensive monitoring.

---

## Prerequisites

### Hardware Requirements
- **GPU**: NVIDIA GPU with at least 24GB VRAM (for vLLM with Qwen3-4B-Instruct)
  - Recommended: RTX 4090, A6000, or better
- **RAM**: 32GB+ system memory
- **Storage**: 100GB+ free disk space (for models, datasets, and vector indices)

### Software Requirements
- **OS**: Ubuntu 22.04+ or compatible Linux distribution
- **Docker**: 24.0+ with Docker Compose v2
- **NVIDIA Drivers**: 535+ with CUDA 12.1+
- **Python**: 3.12 (managed via Docker, or locally with `uv`)

### Accounts & Credentials
- **HuggingFace Hub**: Account with access token for downloading models/datasets
- **Weights & Biases**: Account with API key for experiment tracking (optional but recommended)

---

## Setup Steps

### Step 1: Clone Repository and Checkout Branch

```bash
git clone https://github.com/yourusername/Vietnamese-Medical-RAG-QA-System.git
cd Vietnamese-Medical-RAG-QA-System
git checkout 001-improve-rag-system
```

### Step 2: Configure Environment Variables

Create `.env` file in the project root:

```bash
# HuggingFace Hub
HF_TOKEN=hf_your_token_here

# Weights & Biases (optional)
WANDB_API_KEY=your_wandb_api_key_here

# Database (PostgreSQL)
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_secure_password
POSTGRES_DB=medical_rag

# Qdrant
QDRANT_API_KEY=your_qdrant_api_key  # Optional for local deployment

# Redis
REDIS_PASSWORD=your_redis_password

# JWT Secret for Authentication
JWT_SECRET=your_jwt_secret_key_here

# Model Serving
VLLM_API_BASE=http://vllm:8000
TRITON_API_BASE=http://triton:8001

# Observability
GRAFANA_ADMIN_PASSWORD=your_grafana_password
```

### Step 3: Download Models from HuggingFace

Create `models/` directory and download Qwen3 models:

```bash
mkdir -p models/qwen3

# Login to HuggingFace Hub
huggingface-cli login --token $HF_TOKEN

# Download generation model (vLLM will load this)
huggingface-cli download Qwen/Qwen3-4B-Instruct-2507 --local-dir models/qwen3/generation

# Download embedding model (Triton will serve this)
huggingface-cli download Qwen/Qwen3-Embedding-0.6B --local-dir models/qwen3/embedding

# Download reranker model
huggingface-cli download Qwen/Qwen3-Reranker-0.6B --local-dir models/qwen3/reranker

# Download guardrails model
huggingface-cli download Qwen/Qwen3Guard-Gen-0.6B --local-dir models/qwen3/guardrails
```

**Note**: Total download size is approximately 10GB.

### Step 4: Download Datasets from HuggingFace

```bash
# Download Vietnamese medical corpus dataset
cd backend
python -m backend.scripts.load_dataset --output-dir ./data

# Or manually with Python:
python -c "
from datasets import load_dataset

# Vietnamese Medical Corpus Dataset (comprehensive medical documents for RAG indexing)
# URL: https://huggingface.co/datasets/quannguyen204/vietnamese_medical_corpus_dataset
dataset = load_dataset('quannguyen204/vietnamese_medical_corpus_dataset')
dataset.save_to_disk('data/vietnamese_medical_corpus')
"
```

### Step 5: Initialize Database Schema

Run Alembic migrations to create PostgreSQL tables:

```bash
cd backend
alembic upgrade head
```

Expected output:
```
INFO  [alembic.runtime.migration] Running upgrade  -> 9290fad6ca4e, first version
INFO  [alembic.runtime.migration] Running upgrade 9290fad6ca4e -> XXXX, chainlit schema
```

### Step 6: Start Infrastructure Services

Start PostgreSQL, Qdrant, Elasticsearch, Redis using Docker Compose:

```bash
# Start database services
cd database
docker compose up -d

# Wait for services to be ready
docker compose ps  # Check all services are "Up"

# Test PostgreSQL connection
docker exec -it medical-rag-postgres psql -U postgres -d medical_rag -c "SELECT version();"

# Test Qdrant connection
curl http://localhost:6333/collections

# Test Elasticsearch connection
curl http://localhost:9200/_cluster/health

# Test Redis connection
docker exec -it medical-rag-redis redis-cli ping
```

### Step 7: Start Model Serving Infrastructure

#### 7a. Start vLLM for Generation Model

```bash
# Start vLLM server with Qwen3-4B-Instruct
docker run -d \
  --name vllm-server \
  --gpus all \
  -p 8000:8000 \
  -v $(pwd)/models/qwen3/generation:/models \
  vllm/vllm-openai:latest \
  --model /models \
  --tensor-parallel-size 1 \
  --dtype float16 \
  --max-model-len 8192 \
  --trust-remote-code
```

Verify vLLM is running:
```bash
curl http://localhost:8000/v1/models
```

Expected response:
```json
{
  "object": "list",
  "data": [
    {
      "id": "Qwen3-4B-Instruct-2507",
      "object": "model",
      ...
    }
  ]
}
```

#### 7b. Start Triton Inference Server for Embedding/Reranking/Guardrails

Create Triton model repository structure:

```bash
mkdir -p serving/triton/model_repository

# Create model configs for each Qwen3 model
# (See serving/triton/README.md for detailed config examples)

# Start Triton server
docker run -d \
  --name triton-server \
  --gpus all \
  -p 8001:8001 \
  -p 8002:8002 \
  -v $(pwd)/serving/triton/model_repository:/models \
  nvcr.io/nvidia/tritonserver:24.01-py3 \
  tritonserver --model-repository=/models
```

Verify Triton models are loaded:
```bash
curl http://localhost:8001/v2/models
```

### Step 8: Start Celery Workers

```bash
cd backend
celery -A src.tasks worker --loglevel=info --concurrency=4
```

Expected output:
```
[tasks]
  . message_handler_task
  . chunk_and_index_document
  . fine_tune_model
  . evaluate_model
```

### Step 9: Index Medical Documents

Run the document ingestion task:

```bash
# Index vietnamese_medical_corpus_dataset
curl -X POST http://localhost:8000/indexing/ingest-dataset \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "dataset_name": "quannguyen204/vietnamese_medical_corpus_dataset",
    "doc_type": "medical_qa",
    "max_documents": null
  }'
```

Monitor indexing progress:
```bash
# Get job ID from above response
curl http://localhost:8000/indexing/jobs/{job_id} \
  -H "Authorization: Bearer $JWT_TOKEN"
```

Expected output (when completed):
```json
{
  "job_id": "550e8400-...",
  "status": "completed",
  "result": {
    "documents_indexed": 5000,
    "chunks_indexed": 50000,
    "duration_seconds": 300.5
  }
}
```

Verify Qdrant collection:
```bash
curl http://localhost:6333/collections/medical_documents
```

Verify Elasticsearch index:
```bash
curl http://localhost:9200/medical_documents/_count
```

### Step 10: Start Monitoring Stack

```bash
cd monitoring
docker compose up -d prometheus grafana loki tempo promtail
```

Access dashboards:
- **Grafana**: http://localhost:3000 (admin / $GRAFANA_ADMIN_PASSWORD)
- **Prometheus**: http://localhost:9090
- **Tempo**: http://localhost:3200

Import pre-built Grafana dashboards:
```bash
# Import dashboards from monitoring/grafana/dashboards/
# 1. FastAPI Application Metrics
# 2. Celery Task Metrics
# 3. RAG Pipeline Metrics
# 4. Model Serving Metrics
```

### Step 11: Start Backend API

```bash
cd backend
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

Verify API is running:
```bash
curl http://localhost:8000/docs
```

Expected: OpenAPI documentation page

### Step 12: Start Chainlit Frontend

```bash
cd frontend
chainlit run main.py --host 0.0.0.0 --port 8501
```

Access Chainlit UI: http://localhost:8501

---

## Validation Steps

### 1. Test Authentication

#### Register a new user:
```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "doctor@example.com",
    "password": "SecureP@ss123",
    "display_name": "Dr. Nguyen"
  }'
```

#### Login:
```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "doctor@example.com",
    "password": "SecureP@ss123"
  }'
```

Save the returned `access_token` for subsequent requests.

### 2. Test RAG Query

#### Create a chat session:
```bash
curl -X POST http://localhost:8000/chat/sessions \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Medical Query"
  }'
```

#### Send a message:
```bash
curl -X POST http://localhost:8000/chat/sessions/{session_id}/messages \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Paracetamol có tác dụng phụ gì không?"
  }'
```

Expected response:
```json
{
  "user_message": {
    "id": "...",
    "role": "user",
    "content": "Paracetamol có tác dụng phụ gì không?"
  },
  "assistant_message": {
    "id": "...",
    "role": "assistant",
    "content": "Paracetamol có thể gây ra một số tác dụng phụ như..."
  },
  "retrieved_documents": [
    {
      "title": "Hướng dẫn sử dụng Paracetamol",
      "content": "...",
      "score": 0.87
    }
  ],
  "latency_ms": 1250
}
```

### 3. Test Caching

Send the same query again and verify latency is reduced (cache hit):

```bash
curl -X POST http://localhost:8000/chat/sessions/{session_id}/messages \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Paracetamol có tác dụng phụ gì không?"
  }'
```

Expected: `latency_ms` should be < 500ms (vs ~1250ms for cache miss).

Check Redis cache:
```bash
docker exec -it medical-rag-redis redis-cli KEYS "emb:*"
docker exec -it medical-rag-redis redis-cli KEYS "search:*"
```

### 4. Test Hybrid Search

Verify both Qdrant and Elasticsearch are used:

```bash
# Check Prometheus metrics
curl http://localhost:9090/api/v1/query?query=rag_search_requests_total
```

Expected metrics:
- `rag_search_requests_total{search_type="vector"}` > 0
- `rag_search_requests_total{search_type="keyword"}` > 0
- `rag_search_requests_total{search_type="hybrid"}` > 0

### 5. Test Monitoring

#### Check Prometheus targets:
```
http://localhost:9090/targets
```

Expected: All targets (FastAPI, Celery, vLLM, Triton) should be "UP".

#### Check Grafana dashboards:
```
http://localhost:3000/dashboards
```

Verify:
- RAG Pipeline Metrics dashboard shows request rates, latencies, error rates
- Model Serving Metrics shows vLLM/Triton throughput
- Celery Task Metrics shows task queue lengths

#### Check Loki logs:
```bash
# Query logs via Grafana Explore
# LogQL: {job="fastapi"} |= "RAG"
```

#### Check Tempo traces:
```bash
# Query traces via Grafana Explore
# Search for traces with service.name="backend"
```

### 6. Test Model Fine-tuning (Optional)

Run a fine-tuning job:

```bash
# Fine-tune generation model on combined_medical_qa_dataset
python ml/fine_tuning/train_generation.py \
  --base-model models/qwen3/generation \
  --dataset data/combined_medical_qa_dataset \
  --output-dir models/qwen3/generation-finetuned-v1 \
  --lora-r 16 \
  --lora-alpha 32 \
  --epochs 3
```

Monitor W&B dashboard: https://wandb.ai/your-project

Register fine-tuned model:
```bash
curl -X POST http://localhost:8000/models \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model_name": "Qwen3-4B-Instruct-2507",
    "model_type": "generation",
    "version": "v1.0-medical-qa",
    "huggingface_repo": "your-username/qwen3-medical-qa-v1",
    "training_dataset": "combined_medical_qa_dataset",
    "baseline_metrics": {"accuracy": 0.75, "f1_score": 0.72},
    "finetuned_metrics": {"accuracy": 0.78, "f1_score": 0.76}
  }'
```

Deploy model (if improvement >= 2%):
```bash
curl -X POST http://localhost:8000/models/{model_id}/deploy \
  -H "Authorization: Bearer $JWT_TOKEN"
```

### 7. Test Load Testing (Optional)

Run Locust load test:

```bash
cd testing
locust -f load_tests/rag_loadtest.py --host http://localhost:8000
```

Access Locust UI: http://localhost:8089

Configure:
- **Number of users**: 10
- **Spawn rate**: 1 user/second

Monitor metrics in Grafana during load test.

---

## Troubleshooting

### Issue: vLLM fails to start (GPU memory error)

**Solution**: Reduce `--max-model-len` or use smaller model:
```bash
docker run ... vllm/vllm-openai:latest \
  --model /models \
  --max-model-len 4096  # Reduce from 8192
```

### Issue: Triton model fails to load

**Solution**: Check Triton logs:
```bash
docker logs triton-server
```

Verify model config at `serving/triton/model_repository/{model_name}/config.pbtxt`.

### Issue: PostgreSQL connection refused

**Solution**: Ensure database container is running:
```bash
cd database
docker compose ps
docker compose restart postgres
```

### Issue: Qdrant out of memory

**Solution**: Reduce batch size in indexing task:
```python
# backend/src/tasks.py
BATCH_SIZE = 100  # Reduce from 1000
```

### Issue: Redis cache not working

**Solution**: Verify Redis connection:
```bash
docker exec -it medical-rag-redis redis-cli ping
# Expected: PONG
```

Check Redis password in `.env` matches `docker-compose.yml`.

### Issue: Grafana dashboards show no data

**Solution**: Verify Prometheus is scraping targets:
```bash
curl http://localhost:9090/api/v1/targets
```

Ensure FastAPI app is instrumented with Prometheus metrics:
```python
# backend/src/main.py
from prometheus_client import Counter, Histogram
# ... (metrics should be defined)
```

### Issue: Model serving latency is too high

**Solution**:
1. Enable caching (should already be enabled)
2. Increase vLLM batch size:
   ```bash
   --max-num-batched-tokens 8192
   ```
3. Use quantization for smaller models (Triton):
   - Convert models to FP16 or INT8

---

## Next Steps

1. **Fine-tune models**: Run fine-tuning scripts in `ml/fine_tuning/`
2. **Add more datasets**: Ingest additional medical datasets via `/indexing/ingest-dataset`
3. **Configure alerts**: Set up alerting rules in Prometheus (`monitoring/prometheus/alerts.yml`)
4. **Optimize performance**: Tune chunking parameters, cache TTLs, model serving configs
5. **Scale horizontally**: Deploy multiple Celery workers, vLLM replicas, or Triton instances

---

## Additional Resources

- **Chainlit Documentation**: https://docs.chainlit.io/
- **vLLM Documentation**: https://docs.vllm.ai/
- **Triton Inference Server**: https://docs.nvidia.com/deeplearning/triton-inference-server/
- **Qwen3 Models**: https://huggingface.co/Qwen
- **Prometheus Monitoring**: https://prometheus.io/docs/
- **Grafana Dashboards**: https://grafana.com/docs/

---

## Summary

You now have a fully functional Vietnamese Medical RAG QA System with:

✅ Chainlit UI with authentication
✅ Qwen3 models (generation, embedding, reranking, guardrails)
✅ Hybrid search (Qdrant + Elasticsearch + RRF)
✅ Redis caching layer
✅ Comprehensive monitoring (Prometheus, Loki, Tempo, Grafana)
✅ Model fine-tuning and deployment infrastructure
✅ Load testing capabilities

**Estimated setup time**: 2-3 hours (excluding model downloads)

For questions or issues, refer to the project README or open a GitHub issue.
