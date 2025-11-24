# Vietnamese-Medical-RAG-QA-System Development Guidelines

Auto-generated from all feature plans. Last updated: 2025-11-24

## Active Technologies

- Python 3.12 (001-improve-rag-system)
- Chainlit 2.8.3 (RAG-native UI with OAuth authentication + Audio support)
- FastAPI 0.115.3 (Backend API + Model Serving routing)
- PostgreSQL 18 (Chainlit standard schema only)
- Qdrant (Vector database for embeddings)
- Elasticsearch (Keyword search)
- Redis (Cache + Celery broker)
- vLLM (Remote generation model serving)
- GPU Service (Consolidated: Qwen3 Embedding/Reranking/Guardrails + Whisper-turbo STT)
- faster-whisper (Whisper-turbo with batch inference on GPU)
- ElevenLabs API (Cloud TTS)
- DeepEval + LlamaIndex (RAG evaluation frameworks)

## Dataset

**Primary Dataset**: `quannguyen204/vietnamese_medical_corpus_dataset`
- **URL**: <https://huggingface.co/datasets/quannguyen204/vietnamese_medical_corpus_dataset>
- **Purpose**: Comprehensive Vietnamese medical corpus for RAG indexing
- **Content**: Medical articles, clinical guidelines, drug information, health resources
- **Usage**: Direct loading from HuggingFace Hub via `backend/scripts/load_dataset.py`

## Project Structure

```text
backend/
  config/
    models.yaml      # Model deployment config (HuggingFace repos + STT/TTS)
  src/
    models.py        # Chainlit schema + Document/Chunk models
    database.py
    main.py          # FastAPI app (startup + router registration)
    routers/         # Modular API routers (NEW 2025-11-24)
      __init__.py
      health.py      # Health check + cache stats
      rag.py         # RAG query endpoint
      models.py      # Model inference (embed, rerank, guard)
      audio.py       # Speech-to-speech (STT, TTS, Audio RAG)
      documents.py   # Document management + indexing
    tasks.py         # Celery tasks for RAG pipeline
    core/
      model_config.py  # Config file loader
      model_loader.py  # Model loading utilities for FastAPI serving
    services/
      brain.py       # Generation service (remote vLLM)
      embedding.py   # Embedding service (routes to GPU service)
      rerank.py      # Reranking service (routes to GPU service)
      stt_service.py # Speech-to-text service (routes to GPU service)
      tts_service.py # Text-to-speech service (ElevenLabs)
    scripts/
      evaluate_rag.py  # RAG evaluation with DeepEval/LlamaIndex
  alembic/
    versions/
      001_chainlit_schema.py  # Chainlit standard schema migration
  data/
    eval_dataset.jsonl  # RAG evaluation test dataset
frontend/
  main.py           # Main Chainlit app with audio handlers
  helpers.py        # Backend API calls (RAG + STT + TTS)
  .chainlit/
    config.toml     # OAuth + Audio configuration
database/
  init.sql          # Chainlit schema + documents/chunks
serving/
  vllm/
    entrypoint.sh  # Remote vLLM startup script
  qwen3_models/
    app.py         # GPU service: Qwen3 models + Whisper-turbo STT
    Dockerfile     # CUDA runtime with all models
monitoring/         # Observability stack (Prometheus, Loki, Tempo, Grafana)
testing/            # Load testing (Locust)
```

## Commands

```bash
# Backend
cd backend
uv run alembic upgrade head      # Run migrations
uv run uvicorn src.main:app --reload

# Frontend (Chainlit)
cd frontend
chainlit run main.py

# Database
cd database
docker-compose up -d

# GPU Service (Qwen3 + Whisper-turbo STT)
cd serving/qwen3_models
docker-compose up -d  # Requires GPU with 11GB+ VRAM

# Generation Model Serving (vLLM)
cd serving/vllm
MODEL_NAME=Qwen/Qwen3-4B-Instruct-2507 ./entrypoint.sh

# Tests
pytest
```

## Code Style

- Python 3.12: Follow PEP 8 conventions
- Use `loguru` for logging
- Use `pydantic` for schema validation
- Keep functions simple and focused

## API Router Organization (2025-11-24)

Backend API sử dụng **modular router pattern** với 5 routers:

1. **Health Router** (`health.py`): `/v1/ready`, `/v1/health`, `/v1/cache/stats`
2. **RAG Router** (`rag.py`): `/v1/rag` (main query endpoint)
3. **Models Router** (`models.py`): `/v1/models/embed`, `/v1/models/rerank`, `/v1/models/guard`
4. **Audio Router** (`audio.py`): `/v1/models/stt`, `/v1/models/tts`, `/v1/rag/audio`, `/v1/audio/{filename}`
5. **Documents Router** (`documents.py`): `/v1/documents/*`, `/v1/indexing/*`

**Benefits**: Clear separation of concerns, independent testing, scalable architecture, auto-generated OpenAPI docs grouped by tags.

## Recent Changes (2025-11-24)

### ✅ Speech-to-Speech RAG Integration + GPU Consolidation (UPDATED 2025-11-24)
- **Added**: Full voice input/output pipeline for Vietnamese Medical RAG
- **Features**:
  - Voice input: Whisper-turbo (large-v3-turbo) with **batch inference** on GPU (batch_size=16)
  - Voice output: ElevenLabs API (cloud TTS with multilingual support)
  - Audio caching: Redis cache for STT transcripts (1h TTL) and TTS audio (24h TTL)
  - UI: Chainlit audio features enabled (record button, audio playback)
- **Architecture**:
  - Frontend: `@cl.on_audio_end` handler → upload audio → call backend STT/RAG/TTS
  - Backend: 3 endpoints routing to services:
    - `POST /v1/models/stt`: Audio → GPU service → Text (transcription)
    - `POST /v1/models/tts`: Text → ElevenLabs API → Audio (synthesis)
    - `POST /v1/rag/audio`: Audio → STT → RAG → TTS → Audio (end-to-end)
  - **GPU Service** (`serving/qwen3_models`): Consolidated container for ALL GPU models:
    - Qwen3-Embedding-0.6B (FP16)
    - Qwen3-Reranker-0.6B (FP16)
    - Qwen3Guard-Gen-0.6B (FP16)
    - **Whisper-turbo** (FP16, batch_size=16 for optimal GPU utilization)
  - Shared `/tmp/audio` volume for audio file exchange
- **Configuration**:
  - `backend/src/configs/models.yaml`: Updated `stt` section with Whisper-turbo + batch_size
  - `serving/qwen3_models/docker-compose.yaml`: Added `STT_MODEL` env var
  - Environment variables: `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, `QWEN3_MODELS_ENABLED=true`
- **Performance Optimizations**:
  - **Batch inference**: Whisper-turbo processes audio in batches (16) for 3-5x speedup
  - **GPU memory sharing**: All models on single GPU (reduce idle time)
  - Audio file hashing for cache keys (avoid duplicate processing)
  - Model pre-loading on startup (eliminate cold start latency)
  - Temporary file cleanup (prevent disk bloat)
  - Streaming audio response (reduce perceived latency)
- **Why Consolidation**:
  - Single GPU container reduces deployment complexity
  - Better GPU utilization (models share VRAM efficiently)
  - Simplified networking (no cross-container routing)
  - Faster inference (batch processing + FP16 on GPU)

## Recent Changes (2025-11-19)

### ✅ Serving Architecture Refactoring
- **Removed**: Triton Inference Server for model serving
- **Added**: FastAPI-based model serving for embedding/reranking/guardrails
- **Why**: Simpler deployment, easier debugging, better Python integration
- **Serving Architecture**:
  - **Remote vLLM**: Generation model (Qwen3-4B-Instruct-2507) on GPU server
  - **Local FastAPI**: Embedding, reranking, guardrails models loaded directly in backend
  - **Benefits**: Reduced complexity, lower VRAM footprint, faster iteration

### ✅ RAG Evaluation Framework
- **Added**: Comprehensive evaluation suite with DeepEval + LlamaIndex
- **Metrics**: 
  - Retrieval: Recall@K, nDCG@K, MRR, Precision@K
  - Generation: Faithfulness, Answer Relevance, Correctness
  - Performance: Latency (p50, p95), Token usage
- **Automation**: CI/CD integration for continuous quality monitoring
- **Location**: `backend/scripts/evaluate_rag.py` with test dataset in `backend/data/eval_dataset.jsonl`

### ✅ Model Configuration Refactoring (2025-11-15)
- **Removed**: Database-based model management (FineTunedModel table, API endpoints)
- **Added**: Config file approach (`backend/config/models.yaml`)
- **Why**: Simpler deployment workflow using HuggingFace Hub + GitOps
- **Deployment Process**:
  1. Fine-tune model → Upload to HuggingFace Hub
  2. Update `config/models.yaml` with new repo ID
  3. Commit changes to Git (version control)
  4. Restart backend service to load new config
  5. Optionally restart vLLM with new MODEL_NAME env var

### ✅ Schema Simplification (2025-11-01)
- **Removed**: Custom User, ChatSession, Message tables
- **Added**: Chainlit standard schema (users, threads, steps, elements, feedbacks)
- **Kept**: Simple documents and chunks tables for medical content
- **Authentication**: OAuth only (no passwords, no JWT) - Google & GitHub via Chainlit
- **Session Management**: Handled by Chainlit internally

### ✅ Database
- Migration: `backend/alembic/versions/001_chainlit_schema.py`
- Schema: Chainlit standard (users, threads, steps, elements, feedbacks) + simple documents (id, title, content, metadata) + chunks (id, documentId, chunkIndex, content, metadata)
- Reference: https://docs.chainlit.io/data-layers/sqlalchemy

## Key Principles

1. **Simplicity First**: Use Chainlit standard schema, don't reinvent the wheel
2. **OAuth Only**: No password complexity, use Google/GitHub OAuth
3. **No JWT**: Chainlit handles session management
4. **Essential Attributes**: Keep documents/chunks tables simple (no over-engineering)
5. **External Stores**: Qdrant (vectors), Elasticsearch (keywords), Redis (cache)
6. **Config Over Database**: Model deployment via YAML config file (not database table)
7. **HuggingFace Hub**: Central model registry for fine-tuned models
8. **GitOps**: Version control for model deployment config

## Model Deployment Workflow

### Development
1. Fine-tune model using scripts in `ml/scripts/`
2. Evaluate and log metrics to W&B
3. Upload to HuggingFace Hub with model card

### Deployment
1. Edit `backend/config/models.yaml`:
   ```yaml
   models:
     generation:
       active: "your-org/qwen3-medical-v1"  # Update this line
   ```
2. Commit to Git: `git commit -m "Deploy qwen3-medical-v1"`
3. Restart backend: `systemctl restart rag-backend`
4. Restart vLLM (optional): `docker-compose restart vllm`

### Rollback
1. Revert Git commit: `git revert HEAD`
2. Restart services

## RAG Evaluation

### Running Evaluation
```bash
cd backend
python scripts/evaluate_rag.py \
  --dataset data/eval_dataset.jsonl \
  --output data/eval_results/
```

### Metrics Tracked
- **Retrieval**: Recall@K, nDCG@K, MRR, Precision@K
- **Generation**: Faithfulness, Answer Relevance, Correctness
- **Performance**: Latency (p50, p95), Token usage

### Quality Thresholds
- Recall@5 >= 0.70
- Faithfulness >= 0.80
- Answer Relevance >= 0.75
- p95 Latency <= 5000ms

## References

- Chainlit Documentation: https://docs.chainlit.io
- Chainlit Audio Features: https://docs.chainlit.io/guides/audio
- Chainlit Data Layer: https://docs.chainlit.io/data-layers/sqlalchemy
- Chainlit OAuth: https://docs.chainlit.io/authentication/oauth
- vLLM Documentation: https://docs.vllm.ai
- faster-whisper: https://github.com/SYSTRAN/faster-whisper
- ElevenLabs API: https://elevenlabs.io/docs/api-reference
- DeepEval Documentation: https://docs.confident-ai.com
- LlamaIndex Evaluation: https://docs.llamaindex.ai/en/stable/module_guides/evaluating/
- HuggingFace Hub: https://huggingface.co/docs/hub

<!-- MANUAL ADDITIONS START -->
Whenever you implement something related to Qwen3 models and their GPU service, please refer to the detailed guidelines from Qwen team by these urls for comprehensive guidance on setup, configuration, performance comparison, troubleshooting, and monitoring.:
- Qwen/Qwen3-4B-Instruct-2507: https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507
- Qwen3-Guard-Gen-0.6B: https://huggingface.co/Qwen/Qwen3Guard-Gen-0.6B
- Qwen3-Embedding-0.6B: https://huggingface.co/Qwen/Qwen3-Embedding-0.6B
- Qwen3-Reranker-0.6B: https://huggingface.co/Qwen/Qwen3-Reranker-0.6B

<!-- MANUAL ADDITIONS END -->
