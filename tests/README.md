# Tests Guide (Integration-first)

This repository uses `pytest` with an integration-first approach: tests run in-process against the FastAPI app (`backend.src.main:app`) while pointing to real services (PostgreSQL, Redis, Elasticsearch, Qdrant, vLLM/Qwen3, ElevenLabs). Unit tests can be added later, but initial coverage favors end-to-end functionality.

## Prerequisites
- Real services up and reachable (see `TESTING.md`).
- Environment variables configured (use `.env` as in `TESTING.md`).
- Python 3.12 with `uv` tool available.

## Quick Run (PowerShell)
```powershell
# Run all integration tests
uv run pytest tests/integration -v

# With coverage for backend source
uv run pytest tests/integration -v --cov=backend/src --cov-report=term-missing --cov-report=html

# Open HTML coverage report
Start-Process .\\htmlcov\\index.html
```

## Test Areas
- Health & metrics: `tests/integration/test_health_ready_metrics.py`
- RAG (text): `tests/integration/test_rag_endpoint.py`
- Models API (embed/rerank/guard): `tests/integration/test_models_api.py`
- Documents CRUD: `tests/integration/test_documents_crud.py`
- Audio pipeline (STT, TTS, Audio RAG): `tests/integration/test_audio_pipeline.py`
- Load testing (Locust): `tests/perf/locustfile.py` (see `tests/LOADTEST.md`)

## Notes
- Audio tests are skipped if `sample_audio_vn.wav` is present under `tests/` (preferred) or repo root.
- Folder `testing/` has been consolidated into `tests/`; use `tests/perf/` for Locust and `tests/sample_audio_vn.wav` for audio.
- Tests assume external dependencies are running; failures typically indicate service readiness or credentials issues.
- For selective runs:
```powershell
uv run pytest tests/integration/test_models_api.py -v
uv run pytest -k "rag and not audio" -v
```

## Tox
Run via tox on Python 3.12:
```powershell
uv run tox -e py312
```
This executes pytest with coverage as configured in `tox.ini`.

## Troubleshooting
- Verify `/v1/ready` and `/v1/health` return OK before running tests.
- Check `docker compose` logs for backend and GPU services.
- Ensure API keys (e.g., `ELEVENLABS_API_KEY`) are set for TTS and vLLM URLs for generation models.
