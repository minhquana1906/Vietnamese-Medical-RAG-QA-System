# Vietnamese Medical RAG QA System

[![Release](https://img.shields.io/github/v/release/minhhquana1906/Vietnamese-Medical-RAG-QA-System)](https://img.shields.io/github/v/release/minhhquana1906/Vietnamese-Medical-RAG-QA-System)
[![Build status](https://img.shields.io/github/actions/workflow/status/minhhquana1906/Vietnamese-Medical-RAG-QA-System/main.yml?branch=main)](https://github.com/minhhquana1906/Vietnamese-Medical-RAG-QA-System/actions/workflows/main.yml?query=branch%3Amain)
[![License](https://img.shields.io/github/license/minhhquana1906/Vietnamese-Medical-RAG-QA-System)](https://img.shields.io/github/license/minhhquana1906/Vietnamese-Medical-RAG-QA-System)

A production-ready Retrieval-Augmented Generation (RAG) system designed to answer Vietnamese medical questions with evidence-based accuracy. The system combines domain-specific document retrieval with state-of-the-art language models to support healthcare professionals and the public.

- **Github repository**: <https://github.com/minhhquana1906/Vietnamese-Medical-RAG-QA-System/>
- **Documentation**: <https://minhhquana1906.github.io/Vietnamese-Medical-RAG-QA-System/>

---

## Table of Contents

1. [Overview](#1-overview)
   - 1.1 [Features](#11-features)
   - 1.2 [System Architecture](#12-system-architecture)
2. [Technology Stack](#2-technology-stack)
   - 2.1 [Core Components](#21-core-components)
   - 2.2 [AI/ML Models](#22-aiml-models)
   - 2.3 [Infrastructure](#23-infrastructure)
3. [Installation](#3-installation)
   - 3.1 [Prerequisites](#31-prerequisites)
   - 3.2 [Quick Start](#32-quick-start)
   - 3.3 [Service-by-Service Setup](#33-service-by-service-setup)
4. [Configuration](#4-configuration)
   - 4.1 [Environment Variables](#41-environment-variables)
   - 4.2 [Model Configuration](#42-model-configuration)
5. [Project Structure](#5-project-structure)
6. [RAG Pipeline Details](#6-rag-pipeline-details)
   - 6.1 [Query Processing](#61-query-processing)
   - 6.2 [Hybrid Search](#62-hybrid-search)
   - 6.3 [Reranking](#63-reranking)
   - 6.4 [Response Generation](#64-response-generation)
7. [Evaluation Results](#7-evaluation-results)
   - 7.1 [Retrieval Metrics](#71-retrieval-metrics)
   - 7.2 [Generation Quality Metrics](#72-generation-quality-metrics)
   - 7.3 [Performance Metrics](#73-performance-metrics)
8. [API Reference](#8-api-reference)
9. [Development](#9-development)
   - 9.1 [Code Quality](#91-code-quality)
   - 9.2 [Testing](#92-testing)
10. [Monitoring](#10-monitoring)
11. [License](#11-license)

---

## 1. Overview

### 1.1 Features

- **Hybrid Search**: Combines semantic vector search (Qdrant) with keyword search (Elasticsearch BM25) using Reciprocal Rank Fusion (RRF)
- **Vietnamese Language Optimization**: Custom Vietnamese text analyzer for Elasticsearch with stopwords and tokenization support
- **Multi-Model Architecture**: Separate specialized models for embedding, reranking, guardrails, and generation
- **Speech-to-Speech Pipeline**: Voice input via Whisper-turbo STT and voice output via ElevenLabs TTS
- **OAuth Authentication**: Google and GitHub OAuth integration via Chainlit
- **Production Monitoring**: Full observability stack with Prometheus, Loki, Tempo, and Grafana
- **Content Safety**: Qwen3Guard-based input/output moderation with 9 safety categories
- **Multi-Level Caching**: Redis caching for embeddings, search results, and audio transcripts

### 1.2 System Architecture

```text
                                    +------------------+
                                    |   Chainlit UI    |
                                    |  (OAuth + Audio) |
                                    +--------+---------+
                                             |
                                             v
+----------------------------------------------------------------------------------------------------------+
|                                      FastAPI Backend                                                      |
|  +-------------+  +-------------+  +-------------+  +-------------+  +---------------+                   |
|  | /v1/health  |  | /v1/rag     |  | /v1/models  |  | /v1/audio   |  | /v1/documents |                   |
|  +-------------+  +-------------+  +-------------+  +-------------+  +---------------+                   |
+----------------------------------------------------------------------------------------------------------+
         |                  |                |                |                    |
         v                  v                v                v                    v
+------------------+  +------------+  +------------------+  +------------+  +------------------+
|   Celery Worker  |  |   Redis    |  | Qwen3 GPU Svc   |  |  ElevenLabs|  |   PostgreSQL     |
| (Async Tasks)    |  |   Cache    |  | (Embed/Rerank/  |  |  TTS API   |  | (Chainlit Schema)|
+------------------+  +------------+  |  Guard/STT)     |  +------------+  +------------------+
                                      +------------------+
                                               |
         +-------------------------------------+-------------------------------------+
         |                                     |                                     |
         v                                     v                                     v
+------------------+                  +------------------+                  +------------------+
|     Qdrant       |                  |  Elasticsearch   |                  |   Remote vLLM    |
|  (Vector Store)  |                  | (BM25 Keyword)   |                  | (Qwen3-4B Gen)   |
+------------------+                  +------------------+                  +------------------+
```

---

## 2. Technology Stack

### 2.1 Core Components

| Component | Technology | Version | Purpose |
|-----------|------------|---------|---------|
| Backend Framework | FastAPI | 0.115.3 | REST API with async support |
| Frontend UI | Chainlit | 2.8.3 | Chat interface with OAuth and audio support |
| Task Queue | Celery | 5.4.0 | Async document processing and RAG pipeline |
| Database | PostgreSQL | 18 | User sessions, threads, document metadata |
| Vector Store | Qdrant | 1.15.1 | Semantic similarity search |
| Keyword Search | Elasticsearch | 8.11.0 | BM25 keyword search with Vietnamese analyzer |
| Cache | Redis | 7.2 | Embedding cache, search results, session data |

### 2.2 AI/ML Models

| Model | Repository | Parameters | Purpose |
|-------|------------|------------|---------|
| Generation | Qwen/Qwen3-4B-Instruct-2507 | 4B | Vietnamese medical response generation |
| Embedding | Qwen/Qwen3-Embedding-0.6B | 0.6B | 1024-dim dense embeddings with instruction awareness |
| Reranking | Qwen/Qwen3-Reranker-0.6B | 0.6B | Cross-encoder document scoring |
| Guardrails | Qwen/Qwen3Guard-Gen-0.6B | 0.6B | Content safety moderation (9 categories) |
| Speech-to-Text | faster-whisper (turbo) | - | Vietnamese audio transcription with batch inference |
| Text-to-Speech | ElevenLabs API (eleven_v3) | - | High-quality Vietnamese speech synthesis |

### 2.3 Infrastructure

| Service | Technology | Purpose |
|---------|------------|---------|
| Metrics | Prometheus | Time-series metrics collection |
| Logs | Loki + Promtail | Centralized log aggregation |
| Traces | Tempo + OpenTelemetry | Distributed request tracing |
| Dashboards | Grafana | Unified observability visualization |
| Model Serving | vLLM | High-performance LLM inference with prefix caching |

---

## 3. Installation

### 3.1 Prerequisites

- **Operating System**: Linux (Ubuntu 20.04+ recommended)
- **Python**: 3.12
- **Docker**: 24.0+ with Compose V2
- **GPU**: NVIDIA GPU with 11GB+ VRAM (for local model serving)
- **CUDA**: 12.0+ with cuDNN 8+
- **Package Manager**: uv (recommended) or pip

### 3.2 Quick Start

```bash
# Clone repository
git clone https://github.com/minhquana1906/Vietnamese-Medical-RAG-QA-System.git
cd Vietnamese-Medical-RAG-QA-System

# Create environment file
cp .env.example .env
# Edit .env with your API keys (OPENAI_API_KEY, DEEPSEEK_API_KEY, etc.)

# Install dependencies
make install

# Create Docker network
docker network create medical_rag_network

# Start all services
cd database && docker compose up -d && cd ..
cd backend && docker compose up -d && cd ..
cd frontend && docker compose up -d && cd ..
cd monitoring && docker compose up -d && cd ..

# Optional: Start GPU model service (requires NVIDIA GPU)
cd serving/qwen3_models && docker compose up -d && cd ..
```

### 3.3 Service-by-Service Setup

#### 3.3.1 Database Layer

```bash
cd database
docker compose up -d
# Creates PostgreSQL with Chainlit schema
# Port: 5432
```

#### 3.3.2 Backend Services

```bash
cd backend
docker compose up -d
# Starts: Qdrant (6333), Redis (6379), Elasticsearch (9200), FastAPI (8000), Celery Worker
```

#### 3.3.3 Frontend (Chainlit)

```bash
cd frontend
docker compose up -d
# Starts Chainlit UI on port 8080
```

#### 3.3.4 Monitoring Stack

```bash
cd monitoring
docker compose up -d
# Starts: Prometheus (9090), Loki (3100), Tempo (3200), Grafana (3000)
```

#### 3.3.5 GPU Model Service

```bash
cd serving/qwen3_models
docker compose up -d
# Loads: Embedding, Reranker, Guardrails, Whisper STT on GPU (port 8002)
```

#### 3.3.6 vLLM Generation Service

```bash
cd serving/vllm
export HF_TOKEN=<your-huggingface-token>
./entrypoint.sh
# Starts vLLM with Qwen3-4B-Instruct-2507 on port 8000
```

#### 3.3.7 Database Migration

```bash
cd backend
uv run alembic upgrade head
```

#### 3.3.8 Load Medical Dataset

```bash
cd backend
uv run python scripts/load_dataset.py
# Downloads: quannguyen204/vietnamese_medical_corpus_dataset from HuggingFace
```

---

## 4. Configuration

### 4.1 Environment Variables

Create `.env` file from `.env.example`:

```bash
# Database
POSTGRES_USER=postgresadmin
POSTGRES_PASSWORD=postgresadmin
POSTGRES_DB=medical_rag_db
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=redisadmin

# Elasticsearch
ELASTICSEARCH_HOST=localhost
ELASTICSEARCH_PORT=9200

# Qdrant
QDRANT_HOST=localhost
QDRANT_PORT=6333

# API Keys
HF_TOKEN=<huggingface-token>
OPENAI_API_KEY=<openai-key>
DEEPSEEK_API_KEY=<deepseek-key>
COHERE_API_KEY=<cohere-key>
TAVILY_API_KEY=<tavily-key>
ELEVENLABS_API_KEY=<elevenlabs-key>

# GPU Service
QWEN3_MODELS_URL=http://localhost:8002
QWEN3_MODELS_ENABLED=true
```

### 4.2 Model Configuration

Models are configured via `backend/src/configs/models.yaml`:

```yaml
models:
  generation:
    active: "Qwen/Qwen3-4B-Instruct-2507"
    description: "Main generation model for medical QA"
    
  embedding:
    active: "Qwen/Qwen3-Embedding-0.6B"
    description: "Embedding model for semantic search"
    
  reranking:
    active: "Qwen/Qwen3-Reranker-0.6B"
    description: "Reranking model for document scoring"
    
  guardrails:
    active: "Qwen/Qwen3Guard-Gen-0.6B"
    threshold: 0.7
    description: "Content safety guardrails"
  
  stt:
    active: "turbo"
    device: "cuda"
    compute_type: "float16"
    batch_size: 16

serving:
  vllm_url: "http://vllm:8000"
  vllm_api_key: "vllm"
```

---

## 5. Project Structure

```text
Vietnamese-Medical-RAG-QA-System/
|-- backend/
|   |-- src/
|   |   |-- main.py              # FastAPI application entry point
|   |   |-- models.py            # SQLAlchemy models (Chainlit schema)
|   |   |-- tasks.py             # Celery tasks for RAG pipeline
|   |   |-- configs/
|   |   |   |-- models.yaml      # Model deployment configuration
|   |   |   |-- setup.py         # Pydantic settings
|   |   |   |-- prompt_templates.py
|   |   |-- core/
|   |   |   |-- cache.py         # Redis caching layer
|   |   |   |-- guardrails.py    # Qwen3Guard integration
|   |   |   |-- hybrid_search.py # RRF fusion search
|   |   |   |-- metrics.py       # Prometheus instrumentation
|   |   |   |-- vectorize.py     # Qdrant operations
|   |   |-- routers/
|   |   |   |-- health.py        # Health check endpoints
|   |   |   |-- rag.py           # RAG query endpoint
|   |   |   |-- models.py        # Model inference endpoints
|   |   |   |-- audio.py         # STT/TTS endpoints
|   |   |   |-- documents.py     # Document management
|   |   |-- services/
|   |       |-- brain.py         # Generation service (vLLM)
|   |       |-- embedding.py     # Embedding service
|   |       |-- rerank.py        # Reranking service
|   |       |-- elasticsearch.py # BM25 search service
|   |       |-- chunking.py      # Document chunking
|   |       |-- stt_service.py   # Speech-to-text
|   |       |-- tts_service.py   # Text-to-speech
|   |-- alembic/                 # Database migrations
|   |-- scripts/                 # Utility scripts
|-- frontend/
|   |-- main.py                  # Chainlit application
|   |-- helpers.py               # Backend API calls
|-- serving/
|   |-- qwen3_models/
|   |   |-- app.py               # GPU service (Embed/Rerank/Guard/STT)
|   |-- vllm/
|       |-- entrypoint.sh        # vLLM startup script
|-- monitoring/
|   |-- prometheus/              # Metrics configuration
|   |-- grafana/                 # Dashboard definitions
|   |-- loki/                    # Log aggregation config
|   |-- tempo/                   # Tracing configuration
|-- data/
|   |-- eval_dataset.jsonl       # Evaluation test dataset (100 QA pairs)
|   |-- eval_results/            # Evaluation output reports
|-- scripts/
|   |-- evaluate_rag.py          # RAG evaluation script
|   |-- eval_utils.py            # Evaluation utilities
|-- database/
|   |-- init.sql                 # Chainlit schema initialization
```

---

## 6. RAG Pipeline Details

### 6.1 Query Processing

1. **Guardrails Validation**: Input query is validated using Qwen3Guard-Gen-0.6B
   - Safety categories: Violent, Sexual, PII, Suicide, Jailbreak, etc.
   - Three-tier severity: Safe, Controversial, Unsafe
   
2. **Query Enhancement**: Optional query rewriting for improved retrieval

3. **Intent Detection**: Route between RAG pipeline and external search (Tavily)

### 6.2 Hybrid Search

The system combines two search strategies using Reciprocal Rank Fusion (RRF):

**Vector Search (Qdrant)**:

- Embedding model: Qwen3-Embedding-0.6B (1024 dimensions)
- Instruction-aware: Queries use task instruction prefix
- Distance metric: Cosine similarity

**Keyword Search (Elasticsearch)**:

- Vietnamese analyzer with custom stopwords
- Edge n-gram for partial matching
- BM25 scoring algorithm

**RRF Fusion**:

```text
RRF_score(d) = sum(1 / (k + rank_i(d))) for all search results
```

- Default k = 60
- Combines rankings from both vector and keyword search
- Final top-K documents selected after fusion

### 6.3 Reranking

Cross-encoder reranking using Qwen3-Reranker-0.6B:

- Format: `<Instruct>: {instruction}\n<Query>: {query}\n<Document>: {doc}`
- Output: Yes/No token probabilities for relevance scoring
- Instruction-aware: Custom medical retrieval instructions improve accuracy by 1-5%

### 6.4 Response Generation

Generation using Qwen3-4B-Instruct-2507 via vLLM:

- Context window: 8192 tokens
- Temperature: 0.7
- Top-p: 0.8
- Prefix caching enabled for faster inference

---

## 7. Evaluation Results

Evaluation conducted on 100 Vietnamese medical QA pairs using Ragas v0.3.9 framework with DeepSeek-Chat as the judge model.

### 7.1 Retrieval Metrics

#### Ragas Retrieval Quality

| Metric | Score | Threshold | Status |
|--------|-------|-----------|--------|
| Context Precision | 0.6972 | >= 0.65 | PASS |
| Context Recall | 0.7328 | >= 0.70 | PASS |

#### Traditional Retrieval Metrics

| Metric | Score |
|--------|-------|
| MRR (Mean Reciprocal Rank) | 0.5753 |
| Recall@1 | 0.5300 |
| Recall@3 | 0.7100 |
| Recall@5 | 0.7600 |
| Recall@10 | 0.7600 |
| nDCG@1 | 0.5300 |
| nDCG@3 | 0.5790 |
| nDCG@5 | 0.5894 |
| nDCG@10 | 0.5894 |
| Precision@1 | 0.5300 |
| Precision@3 | 0.2367 |
| Precision@5 | 0.1520 |
| Precision@10 | 0.0760 |

### 7.2 Generation Quality Metrics

| Metric | Score | Threshold | Status |
|--------|-------|-----------|--------|
| Faithfulness | 0.8363 | >= 0.80 | PASS |
| Answer Relevancy | 0.7679 | >= 0.75 | PASS |

### 7.3 Performance Metrics

| Metric | Value |
|--------|-------|
| Average End-to-End Latency | 3176.30 ms |
| Average Embedding Latency | 23.45 ms |
| Average Retrieval Latency | 92.66 ms |
| Average Reranking Latency | 864.99 ms |
| Average Generation Latency | 2195.20 ms |
| P50 Latency | 3035.71 ms |
| P95 Latency | 5543.36 ms |

#### Threshold Validation Summary

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| Context Recall | >= 0.70 | 0.7328 | PASS |
| Context Precision | >= 0.65 | 0.6972 | PASS |
| Faithfulness | >= 0.80 | 0.8363 | PASS |
| Answer Relevancy | >= 0.75 | 0.7679 | PASS |
| Recall@5 | >= 0.70 | 0.7600 | PASS |
| P95 Latency | <= 10000ms | 5543.36ms | PASS |
| P50 Latency | <= 5000ms | 3035.71ms | PASS |

---

## 8. API Reference

### Health Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/ready` | GET | Readiness probe |
| `/v1/health` | GET | Health check with service status |
| `/v1/cache/stats` | GET | Redis cache statistics |

### RAG Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/rag` | POST | Main RAG query endpoint |
| `/v1/rag/audio` | POST | Voice-to-voice RAG pipeline |

### Model Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/models/embed` | POST | Generate embeddings |
| `/v1/models/rerank` | POST | Rerank documents |
| `/v1/models/guard` | POST | Content safety check |
| `/v1/models/stt` | POST | Speech-to-text transcription |
| `/v1/models/tts` | POST | Text-to-speech synthesis |

### Document Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/documents` | GET | List all documents |
| `/v1/documents` | POST | Create document |
| `/v1/documents/{id}` | GET | Get document by ID |
| `/v1/documents/{id}` | DELETE | Delete document |
| `/v1/indexing/ingest-dataset` | POST | Ingest dataset from HuggingFace |
| `/v1/indexing/jobs/{id}` | GET | Get indexing job status |

---

## 9. Development

### 9.1 Code Quality

```bash
# Install development dependencies
make install

# Run linting and formatting
make check

# Format code
make format
```

Tools used:

- **Ruff**: Linting and formatting (replaces Black, isort, flake8)
- **MyPy**: Static type checking
- **Pre-commit**: Git hooks for code quality

### 9.2 Testing

```bash
# Run all tests
make test

# Run with coverage
make test-cov

# Run unit tests only
make test-unit

# Run integration tests
make test-integration
```

### 9.3 Running Evaluation

```bash
# Run RAG evaluation
uv run scripts/evaluate_rag.py \
    --dataset data/eval_dataset.jsonl \
    --output data/eval_results/ \
    --judge-model deepseek-chat \
    --top-k 5

# Generate synthetic test dataset
uv run scripts/generate_ragas_testset.py \
    --num-samples 100 \
    --output data/eval_dataset.jsonl
```

---

## 10. Monitoring

### Accessing Dashboards

| Service | URL | Credentials |
|---------|-----|-------------|
| Grafana | `http://localhost:3000` | admin/admin |
| Prometheus | `http://localhost:9090` | - |
| Chainlit UI | `http://localhost:8080` | OAuth (Google/GitHub) |

### Key Metrics

**RAG Pipeline**:

- `rag_search_requests_total{search_type}`: Search request count
- `rag_search_duration_seconds{search_type}`: Search latency histogram

**Model Inference**:

- `model_inference_duration_seconds{model_type}`: Inference latency
- `model_inference_total{model_type,status}`: Inference request count
- `gpu_memory_used_bytes{device}`: GPU memory usage

**Cache**:

- `cache_hits_total{cache_type}`: Cache hit count
- `cache_misses_total{cache_type}`: Cache miss count

**Voice Pipeline**:

- `voice_pipeline_duration_seconds{stage}`: STT/TTS latency
- `voice_errors_total{stage,error_type}`: Voice pipeline errors

---

## 11. License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

---

## Authors

- **Quan Nguyen** - [quann1906@gmail.com](mailto:quann1906@gmail.com)

## Dataset

Primary dataset: [quannguyen204/vietnamese_medical_corpus_dataset](https://huggingface.co/datasets/quannguyen204/vietnamese_medical_corpus_dataset)

## References

- [Chainlit Documentation](https://docs.chainlit.io)
- [vLLM Documentation](https://docs.vllm.ai)
- [Qwen3 Models](https://huggingface.co/Qwen)
- [Ragas Evaluation Framework](https://docs.ragas.io)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
