# Vietnamese-Medical-RAG-QA-System Development Guidelines

Auto-generated from all feature plans. Last updated: 2025-11-15

## Active Technologies

- Python 3.12 (001-improve-rag-system)
- Chainlit 1.3.2 (RAG-native UI with OAuth authentication)
- FastAPI 0.112.2 (Backend API)
- PostgreSQL 18 (Chainlit standard schema only)
- Qdrant (Vector database for embeddings)
- Elasticsearch (Keyword search)
- Redis (Cache + Celery broker)
- vLLM (Generation model serving)
- Triton Inference Server (Embedding/Reranking/Guardrails serving)

## Project Structure

```text
backend/
  config/
    models.yaml      # Model deployment config (HuggingFace repos)
  src/
    models.py        # Chainlit schema + Document/Chunk models
    database.py
    main.py          # FastAPI endpoints (RAG only, no model management)
    tasks.py         # Celery tasks for RAG pipeline
    core/
      model_config.py  # Config file loader
    services/
      brain.py       # Generation service (reads from config)
      embedding.py   # Embedding service (reads from config)
      rerank.py      # Reranking service (reads from config)
  alembic/
    versions/
      001_chainlit_schema.py  # Chainlit standard schema migration
frontend/
  chainlit.py       # Main Chainlit app
  .chainlit/
    config.toml     # OAuth configuration
database/
  init.sql          # Chainlit schema + documents/chunks
ml/                 # Fine-tuning workflows
serving/
  vllm/
    entrypoint.sh  # vLLM startup script
  triton/
    models/          # Triton model configs (embedding, reranker, guard)
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
chainlit run chainlit.py

# Database
cd database
docker-compose up -d

# Model Serving
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

## Recent Changes (2025-11-15)

### ✅ Model Configuration Refactoring
- **Removed**: Database-based model management (FineTunedModel table, API endpoints)
- **Added**: Config file approach (`backend/config/models.yaml`)
- **Why**: Simpler deployment workflow using HuggingFace Hub + GitOps
- **Deployment Process**:
  1. Fine-tune model → Upload to HuggingFace Hub
  2. Update `config/models.yaml` with new repo ID
  3. Commit changes to Git (version control)
  4. Restart backend service to load new config
  5. Optionally restart vLLM/Triton with new MODEL_NAME env var

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

## References

- Chainlit Documentation: https://docs.chainlit.io
- Chainlit Data Layer: https://docs.chainlit.io/data-layers/sqlalchemy
- Chainlit OAuth: https://docs.chainlit.io/authentication/oauth
- vLLM Documentation: https://docs.vllm.ai
- Triton Inference Server: https://github.com/triton-inference-server
- HuggingFace Hub: https://huggingface.co/docs/hub

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
