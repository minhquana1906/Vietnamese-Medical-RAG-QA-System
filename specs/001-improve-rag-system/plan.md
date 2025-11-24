# Implementation Plan: RAG System Comprehensive Improvements

**Branch**: `001-improve-rag-system` | **Date**: 2025-10-31 | **Updated**: 2025-11-01 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-improve-rag-system/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

> **📝 Schema Update (2025-11-01)**: Simplified to use Chainlit standard schema. OAuth-only (no passwords/JWT). Simple `documents` table (id, title, content, metadata). See [SCHEMA_SIMPLIFICATION.md](./SCHEMA_SIMPLIFICATION.md).

## Summary

Comprehensive upgrade of the Vietnamese Medical RAG QA System featuring:

1. **Chainlit UI Migration**: Replace Streamlit with RAG-native Chainlit interface supporting OAuth authentication (Google, GitHub only), persistent chat sessions via Chainlit standard schema, and conversation history management
2. **Qwen3 Model Fine-tuning Pipeline**: Establish baseline metrics, fine-tune generation (Qwen3-4B-Instruct-2507) and embedding (Qwen3-Embedding-0.6B) models on Vietnamese medical datasets, evaluate improvements, and serve all 4 Qwen3 models (generation via vLLM, embedding/reranking/guardrails via Triton Inference Server)
3. **Hybrid Search Implementation**: Combine vector search (Qdrant) with keyword search (Elasticsearch) using Reciprocal Rank Fusion (RRF) for improved document retrieval
4. **Dataset Integration**: Load and index combined medical dataset with improved metadata, chunk management, and fine-tuned embeddings
5. **Performance Optimization**: Implement Redis-based caching layer for embeddings and search results
6. **Observability Stack**: Deploy Prometheus (metrics), Promtail+Loki (logs), Tempo (traces), and Grafana (visualization with pre-built dashboards) for comprehensive monitoring
7. **Performance Validation**: Conduct stress and load testing using Locust to validate system capacity and identify bottlenecks

**Technical Approach**: Build on existing FastAPI + Celery architecture while replacing Streamlit frontend, upgrading to fine-tuned Qwen3 models with fallback to OpenAI/Cohere, implementing hybrid retrieval, and establishing production-grade observability. All artifacts (models, datasets) managed via HuggingFace Hub with W&B for experiment tracking.

## Technical Context

**Language/Version**: Python 3.12
**Primary Dependencies**:
- **Backend**: FastAPI 0.112.2, Celery 5.4.0, Alembic 1.16.5 (migrations), SQLAlchemy 1.4.54
- **Frontend**: Chainlit 1.3.2 (replacing Streamlit 1.36.0)
- **Vector DB**: Qdrant 1.10.1 (qdrant/qdrant:v1.15.1 Docker image)
- **Keyword Search**: Elasticsearch 8.11.0 (docker.elastic.co/elasticsearch/elasticsearch:8.11.0)
- **Cache/Queue**: Redis 7.2-bookworm (cache + Celery broker)
- **ML Stack**:
  - vLLM (latest) for Qwen3-4B-Instruct-2507 serving
  - NVIDIA Triton Inference Server (latest) for embedding/reranking/guardrails
  - PyTorch + transformers + peft (LoRA/QLoRA fine-tuning)
  - bitsandbytes (quantization for VRAM efficiency)
- **Monitoring**: Prometheus, Promtail, Loki, Tempo, Grafana 12.2
- **Load Testing**: Locust
- **ML Ops**: HuggingFace Hub (model/dataset registry), W&B (experiment tracking)
- **RAG Framework**: LlamaIndex (for LLM and RAG operations)

**Storage**:
- PostgreSQL 18-bookworm (relational data: users, chat sessions per Chainlit schema)
- Qdrant (vector embeddings for semantic search)
- Elasticsearch (inverted index for keyword search)
- Redis (cache + task queue)
- HuggingFace Hub (model artifacts, datasets)

**Testing**: Manual validation during MVP phase (no automated tests per constitution)

**Target Platform**: Linux server with GPU (vast.ai rented GPU instances)

**Project Type**: Web application (FastAPI backend + Chainlit frontend)

**Performance Goals**:
- Query response: <5 seconds (p95)
- Concurrent users: 100+ with <1% error rate
- Cache hit rate: ≥30% after warm-up
- Fine-tuned models: 2-5% improvement over baseline

**Constraints**:
- Single GPU instance on vast.ai (VRAM budget management required)
- vLLM for generation model (GPU-optimized inference)
- Triton for smaller models (efficient batching for embedding/reranking/guardrails)
- LoRA/QLoRA fine-tuning to minimize VRAM usage
- Fallback to OpenAI (chat/embedding) and Cohere (reranking) when Qwen3 models unavailable

**Scale/Scope**:
- ~100 concurrent users during testing
- ~50-100K medical documents indexed
- 4 Qwen3 models served simultaneously
- 7 major feature phases (P1-P7)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### MVP Phase Compliance

- **✅ MVP First**: Feature prioritizes working functionality over production standards
- **✅ Modular Architecture**: Implementation follows `backend/src/{services,core,configs}` structure
- **✅ No TDD Required**: Tests are NOT required during MVP phase
- **✅ Minimal Documentation**: Documentation kept concise and purpose-driven
- **✅ Working Code Priority**: Extends existing code or marks legacy replacements
- **✅ Async Execution**: Long operations delegated to Celery tasks when applicable
- **✅ Structured Logging**: Uses Loguru for observability

### Technology Stack Verification

- **Language**: Python 3.12 ✅
- **Backend**: FastAPI 0.112.2 ✅
- **Frontend**: Chainlit (replacing Streamlit) ✅ - RAG-native UI
- **Vector DB**: Qdrant 1.10.1 ✅
- **Cache/Queue**: Redis 7.2-bookworm + Celery 5.4.0 ✅
- **Search**: Elasticsearch 8.11.0 ✅ - Hybrid search with RRF
- **LLM**: Qwen3 models (fine-tuned) + OpenAI/Cohere fallback ✅
- **Model Serving**: vLLM (generation) + Triton (embedding/reranking/guardrails) ✅
- **Monitoring**: Prometheus + Loki + Tempo + Grafana ✅
- **Database**: PostgreSQL 18-bookworm ✅
- **ML Ops**: HuggingFace Hub + W&B ✅

### Violations & Justifications

> **Fill ONLY if feature violates constitution principles**

| Violation | Why Needed | Mitigation |
|-----------|------------|------------|
| Multiple new infrastructure components (vLLM, Triton, monitoring stack) | Essential for production-grade serving and observability; cannot achieve performance goals with current setup | Phased rollout (P1-P7), leverage existing Celery async pattern, keep OpenAI/Cohere as fallback |
| Fine-tuning notebooks alongside scripts | Experimentation requires iterative exploration; notebooks enable faster iteration | Scripts for production, notebooks for research; both committed for reproducibility |
| Extensive monitoring stack (4 components) | Observability requirements (FR-040 to FR-049) mandate metrics, logs, and traces | Use pre-built Grafana dashboards to minimize configuration overhead |

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
backend/
├── src/
│   ├── models.py                    # SQLAlchemy models (User, ChatSession, Message, Document, Chunk)
│   ├── database.py                  # Database connection and session management
│   ├── main.py                      # FastAPI app (startup logic + router registration)
│   ├── tasks.py                     # Celery tasks (RAG pipeline, indexing)
│   ├── utils.py                     # Helper utilities
│   ├── routers/                     # NEW (2025-11-24): Modular API routers
│   │   ├── __init__.py
│   │   ├── health.py                # Health check + cache stats endpoints
│   │   ├── rag.py                   # RAG query endpoint
│   │   ├── models.py                # Model inference endpoints (embed, rerank, guard)
│   │   ├── audio.py                 # Speech-to-speech endpoints (STT, TTS, Audio RAG)
│   │   └── documents.py             # Document management + indexing endpoints
│   ├── configs/
│   │   ├── __init__.py
│   │   ├── setup.py                 # Settings (updated for new stack)
│   │   ├── templates.py             # Prompt templates
│   │   ├── celery_config.py
│   │   └── logging_config.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── vectorize.py             # Qdrant operations
│   │   ├── cache.py                 # Redis cache operations (enhanced)
│   │   ├── hybrid_search.py         # NEW: RRF hybrid search implementation
│   │   └── guardrails.py            # NEW: Qwen3Guard integration
│   ├── services/
│   │   ├── __init__.py
│   │   ├── brain.py                 # LLM operations (updated for Qwen3)
│   │   ├── agent.py                 # Agent operations
│   │   ├── chunking.py              # Document chunking (improved strategy)
│   │   ├── rerank.py                # Reranking (Qwen3 + Cohere fallback)
│   │   ├── summarizer.py
│   │   ├── embedding.py             # NEW: Qwen3 embedding service
│   │   └── elasticsearch.py         # NEW: Elasticsearch keyword search
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── schema.py                # Pydantic schemas (updated)
│   │   └── chainlit_schema.py       # NEW: Chainlit-specific schemas
│   └── functions/
│       ├── __init__.py
│       ├── calculator.py
│       ├── helper.py
│       ├── templates.py
│       └── web_search.py
├── alembic/
│   ├── versions/
│   │   ├── 9290fad6ca4e_first_version.py
│   │   └── XXXX_chainlit_schema.py  # NEW: Migration for Chainlit schema
│   ├── env.py
│   └── script.py.mako
├── scripts/
│   ├── init_nltk.py
│   ├── load_dataset.py              # NEW: HuggingFace dataset loader
│   └── migrate_conversations.py     # NEW: Migrate old conversations
├── docker-compose.yml               # Updated with new services
├── Dockerfile
└── alembic.ini

frontend/
├── chainlit.py                      # NEW: Main Chainlit app
├── chainlit_config.py               # NEW: Chainlit configuration
├── .chainlit/
│   └── config.toml                  # NEW: Chainlit settings
├── public/                          # NEW: Static assets
├── components/                      # NEW: Custom Chainlit components
└── docker-compose.yml               # NEW: Frontend container

ml/                                  # NEW: Machine learning workflows
├── notebooks/
│   ├── 01_generation_baseline.ipynb
│   ├── 02_generation_finetune.ipynb
│   ├── 03_embedding_baseline.ipynb
│   ├── 04_embedding_finetune.ipynb
│   └── 05_evaluation.ipynb
├── scripts/
│   ├── train_generation.py          # LoRA/QLoRA fine-tuning for generation
│   ├── train_embedding.py           # Fine-tuning for embedding
│   ├── evaluate_generation.py       # Evaluation scripts
│   ├── evaluate_embedding.py
│   └── upload_to_hub.py             # HuggingFace Hub upload
├── configs/
│   ├── generation_lora_config.yaml
│   └── embedding_lora_config.yaml
└── requirements.txt

serving/                             # NEW: Model serving configurations
├── vllm/
│   ├── entrypoint.sh
│   ├── config.json
│   └── Dockerfile
├── triton/
│   ├── models/
│   │   ├── qwen3_embedding/
│   │   │   ├── config.pbtxt
│   │   │   └── 1/model.py
│   │   ├── qwen3_reranker/
│   │   │   ├── config.pbtxt
│   │   │   └── 1/model.py
│   │   └── qwen3_guard/
│   │       ├── config.pbtxt
│   │       └── 1/model.py
│   └── docker-compose.yml
└── README.md

monitoring/                          # NEW: Observability stack
├── prometheus/
│   ├── prometheus.yml
│   └── alerts.yml
├── loki/
│   └── loki-config.yaml
├── tempo/
│   └── tempo-config.yaml
├── promtail/
│   └── promtail-config.yaml
├── grafana/
│   ├── dashboards/                  # Pre-built dashboard JSONs
│   │   ├── rag_pipeline.json
│   │   ├── model_serving.json
│   │   └── system_health.json
│   └── datasources.yaml
└── docker-compose.yml

testing/                             # NEW: Performance testing
├── locustfile.py                    # Load test scenarios
├── stress_test.py                   # Stress test scenarios
└── results/                         # Test result outputs

database/
├── docker-compose.yml               # PostgreSQL + existing DBs
└── init.sql

.github/
├── prompts/                         # Existing speckit prompts
└── workflows/                       # CI/CD workflows

docs/                                # Minimal documentation
└── setup_instructions.md            # NEW: Setup guide for new components
```

**Structure Decision**: Web application with separated backend/frontend + new ML and serving directories. Backend maintains existing `src/` structure with enhancements. New `ml/` directory for fine-tuning workflows (notebooks + scripts). New `serving/` for model deployment configs. New `monitoring/` for observability stack. New `testing/` for load/stress tests. Frontend migrates from `frontend/main.py` (Streamlit) to `frontend/chainlit.py` (Chainlit).

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Multiple new infrastructure components (vLLM, Triton, Prometheus, Loki, Tempo) | Production requirements demand high-performance model serving (vLLM for generation, Triton for batched inference) and comprehensive observability (metrics, logs, traces) | Using only OpenAI APIs: loses control over model quality and incurs high costs; Using simple logging: insufficient for debugging distributed RAG pipeline; Single serving approach: vLLM optimized for generation, Triton better for smaller models |
| New ML directory with notebooks + scripts | Fine-tuning requires experimentation (notebooks) and reproducible training (scripts); Baseline/evaluation workflows need structured comparison | Scripts only: loses exploratory capability for hyperparameter tuning; Notebooks only: not reproducible for production training runs |
| Monitoring stack (4 components) | FR-040 to FR-049 mandate metrics (Prometheus), logs (Loki), traces (Tempo), and visualization (Grafana); RAG pipeline has multiple stages requiring end-to-end observability | Simple logging to files: no queryable metrics or distributed tracing; Single tool (e.g., ELK): user specifically requested Prometheus+Loki+Tempo+Grafana stack |
