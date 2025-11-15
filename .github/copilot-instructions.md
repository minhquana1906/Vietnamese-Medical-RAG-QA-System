# Vietnamese-Medical-RAG-QA-System Development Guidelines

Auto-generated from all feature plans. Last updated: 2025-11-01

## Active Technologies

- Python 3.12 (001-improve-rag-system)
- Chainlit 1.3.2 (RAG-native UI with OAuth authentication)
- FastAPI 0.112.2 (Backend API)
- PostgreSQL 18 (Chainlit standard schema)
- Qdrant (Vector database for embeddings)
- Elasticsearch (Keyword search)
- Redis (Cache + Celery broker)

## Project Structure

```text
backend/
  src/
    models.py         # Chainlit schema + Document/Chunk models
    database.py
    main.py          # FastAPI endpoints (no password auth)
    tasks.py         # Celery tasks for RAG pipeline
    configs/
    core/
    services/
    schemas/
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
serving/            # Model serving configs (vLLM, Triton)
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

# Tests
pytest
```

## Code Style

- Python 3.12: Follow PEP 8 conventions
- Use `loguru` for logging
- Use `pydantic` for schema validation
- Keep functions simple and focused

## Recent Changes (2025-11-01)

### ✅ Schema Simplification
- **Removed**: Custom User, ChatSession, Message tables
- **Added**: Chainlit standard schema (users, threads, steps, elements, feedbacks)
- **Kept**: Simple documents and chunks tables for medical content
- **Authentication**: OAuth only (no passwords, no JWT) - Google & GitHub via Chainlit
- **Session Management**: Handled by Chainlit internally

### ✅ Database
- Migration: `backend/alembic/versions/001_chainlit_schema.py`
- Schema: Chainlit standard (users, threads, steps, elements, feedbacks) + simple documents (id, title, content, metadata) + chunks (id, documentId, chunkIndex, content, metadata)
- Reference: https://docs.chainlit.io/data-layers/sqlalchemy

### ⏳ TODO
- Remove password authentication endpoints from `backend/src/main.py`
- Configure OAuth in `frontend/.chainlit/config.toml`
- Update spec.md, plan.md, tasks.md with simplified architecture

## Key Principles

1. **Simplicity First**: Use Chainlit standard schema, don't reinvent the wheel
2. **OAuth Only**: No password complexity, use Google/GitHub OAuth
3. **No JWT**: Chainlit handles session management
4. **Essential Attributes**: Keep documents/chunks tables simple (no over-engineering)
5. **External Stores**: Qdrant (vectors), Elasticsearch (keywords), Redis (cache)

## References

- Chainlit Documentation: https://docs.chainlit.io
- Chainlit Data Layer: https://docs.chainlit.io/data-layers/sqlalchemy
- Chainlit OAuth: https://docs.chainlit.io/authentication/oauth
- Schema Changes: `/specs/001-improve-rag-system/SCHEMA_SIMPLIFICATION.md`

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
