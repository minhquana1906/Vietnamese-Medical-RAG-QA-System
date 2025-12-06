# Test Execution Guide (Unified)

This single guide unifies service setup, integration testing, and load testing. It merges prior documents: tests README (integration-first) and Locust load testing instructions.

## Prerequisites

- Real services up and reachable (PostgreSQL, Redis, Elasticsearch, Qdrant, vLLM/Qwen3, ElevenLabs)
- NVIDIA GPU recommended for model services; CPU fallback supported
- Docker Desktop (Windows) or Docker Engine (Linux) with Compose V2
- Verified API keys: `HF_TOKEN`, `ELEVENLABS_API_KEY`, optionally `OPENAI_API_KEY`, `TAVILY_API_KEY`
- `.env` created from `.env.example`
- Python 3.12 with `uv` tool available

## Environment Configuration

Update `.env` with GPU and service settings:

```
QWEN3_MODELS_ENABLED=true
QWEN3_MODELS_URL=http://localhost:8002
HF_TOKEN=<your-hf-token>
ELEVENLABS_API_KEY=<your-elevenlabs-key>
# Optional
OPENAI_API_KEY=<your-openai-key>
TAVILY_API_KEY=<your-tavily-key>
```

## Bring Up Services (Windows PowerShell)

```powershell
# From repo root
docker network create medical_rag_network

Push-Location "database"; docker compose up -d; Pop-Location
Push-Location "backend"; docker compose up -d; Pop-Location
Push-Location "frontend"; docker compose up -d; Pop-Location
Push-Location "monitoring"; docker compose up -d; Pop-Location

# GPU services
Push-Location "serving/qwen3_models"; docker compose up -d; Pop-Location

# vLLM service (ensure HF_TOKEN set in env before running entrypoint)
Push-Location "serving/vllm"; ./entrypoint.sh; Pop-Location
```

Ports:
- Backend API `8000`
- Chainlit UI `8080`
- PostgreSQL `5432`, Redis `6379`, Elasticsearch `9200`, Qdrant `6333`
- GPU models service `8002`, vLLM `8000/8001` per config
- Prometheus `9090`, Grafana `3000`

## Readiness & Smoke Checks

```powershell
Invoke-WebRequest -UseBasicParsing http://localhost:8000/v1/ready
Invoke-WebRequest -UseBasicParsing http://localhost:8000/v1/health
Invoke-WebRequest -UseBasicParsing http://localhost:8000/v1/cache/stats
```

Open Chainlit UI: `http://localhost:8080`

## Load a Small Dataset

```powershell
Push-Location "backend"; uv run python scripts/load_dataset.py; Pop-Location
```

Validate indexing:
- Documents appear in Chainlit UI or via `/v1/documents`
- Chunks visible and searchable
- Qdrant/Elasticsearch logs show inserts

## Text RAG Samples

Try 3–5 Vietnamese medical queries in Chainlit, e.g.:
- "Triệu chứng điển hình của viêm phổi là gì?"
- "Thuốc hạ sốt nào an toàn cho trẻ em?"
- "Khi nào cần xét nghiệm HbA1c cho bệnh nhân tiểu đường?"

Check:
- Citations (document sources)
- Faithfulness and relevancy of answers
- Latency (UI and Prometheus metrics)

## Hybrid Search Variants

Run keyword-heavy vs semantic-heavy queries; confirm diverse top-K via RRF. Repeat a query to observe Redis cache hits in `/v1/cache/stats`.

## Reranking Checks

- Ensure reranker enabled in config
- Compare responses with reranker off (if supported)
- Call `/v1/models/rerank` to inspect score distribution

## Guardrails Tests

Submit unsafe/borderline queries and verify behavior:
- Violent/sexual/PII/jailbreak examples
- Confirm block/warn/rewrite per `/v1/models/guard`

## Audio Pipeline (GPU STT + TTS)

Record a short Vietnamese question in Chainlit.
Validate:
- STT transcript accuracy
- Text RAG answer
- TTS playback; audio file accessible in UI

## Observability Checks

- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000`
- Optional: Loki logs and Tempo traces

## Troubleshooting

- If GPU services fail, verify Docker Desktop GPU support or use Linux
- CPU fallback: set `QWEN3_MODELS_ENABLED=false` and restart backend
- Check env variables and container logs for vLLM/GPU readiness

---

## Tests Guide (Integration-first)

This repository uses `pytest` with an integration-first approach: tests run in-process against the FastAPI app (`backend.src.main:app`) while pointing to real services.

### Quick Run (PowerShell)
```powershell
# Run all integration tests
uv run pytest tests/integration -v

# With coverage for backend source
uv run pytest tests/integration -v --cov=backend/src --cov-report=term-missing --cov-report=html

# Open HTML coverage report
Start-Process .\htmlcov\index.html
```

### Test Areas
- Health & metrics: `tests/integration/test_health_ready_metrics.py`
- RAG (text): `tests/integration/test_rag_endpoint.py`
- Models API (embed/rerank/guard): `tests/integration/test_models_api.py`
- Documents CRUD: `tests/integration/test_documents_crud.py`
- Audio pipeline (STT, TTS, Audio RAG): `tests/integration/test_audio_pipeline.py`
- Load testing (Locust): `tests/perf/locustfile.py`

### Notes
- Audio tests use `tests/sample_audio_vn.wav` (preferred) or repo root
- `testing/` consolidated into `tests/`; use `tests/perf/` for Locust
- Tests assume external dependencies are running; failures typically indicate readiness or credentials

### Selective Runs
```powershell
uv run pytest tests/integration/test_models_api.py -v
uv run pytest -k "rag and not audio" -v
```

### Tox
```powershell
uv run tox -e py312
```
Executes pytest with coverage as configured in `tox.ini`.

### Troubleshooting
- Verify `/v1/ready` and `/v1/health` return OK
- Check `docker compose` logs for backend and GPU services
- Ensure API keys (e.g., `ELEVENLABS_API_KEY`) are set for TTS and vLLM URLs

---

## Endpoint Test Matrix (Quick Commands)

Use these PowerShell commands to validate core endpoints quickly.

- `/v1/ready`:
```powershell
Invoke-WebRequest -UseBasicParsing http://localhost:8000/v1/ready
```
- `/v1/health`:
```powershell
Invoke-WebRequest -UseBasicParsing http://localhost:8000/v1/health
```
- `/v1/cache/stats`:
```powershell
Invoke-WebRequest -UseBasicParsing http://localhost:8000/v1/cache/stats
```
- `/v1/rag` (text):
```powershell
$body = @{ query = "Triệu chứng điển hình của viêm phổi là gì?"; top_k = 5; return_sources = $true } | ConvertTo-Json
Invoke-WebRequest -UseBasicParsing -Method POST -ContentType "application/json" -Body $body http://localhost:8000/v1/rag
```
- `/v1/rag/audio` (audio file upload):
```powershell
$filePath = "sample_audio_vn.wav" # provide a short Vietnamese recording
$form = @{ file = Get-Item $filePath; top_k = 5; return_sources = "true" }
Invoke-WebRequest -UseBasicParsing -Method POST -Form $form http://localhost:8000/v1/rag/audio
```
- `/v1/models/embed`:
```powershell
$body = @{ text = "viêm phổi" } | ConvertTo-Json
Invoke-WebRequest -UseBasicParsing -Method POST -ContentType "application/json" -Body $body http://localhost:8000/v1/models/embed
```
- `/v1/models/rerank`:
```powershell
$body = @{ query = "viêm phổi"; documents = @("Triệu chứng gồm ho, sốt, khó thở", "Định nghĩa bệnh...", "Điều trị bằng kháng sinh") } | ConvertTo-Json
Invoke-WebRequest -UseBasicParsing -Method POST -ContentType "application/json" -Body $body http://localhost:8000/v1/models/rerank
```
- `/v1/models/guard`:
```powershell
$body = @{ text = "Cách chế tạo chất nổ?" } | ConvertTo-Json
Invoke-WebRequest -UseBasicParsing -Method POST -ContentType "application/json" -Body $body http://localhost:8000/v1/models/guard
```
- `/v1/models/stt`:
```powershell
$filePath = "sample_audio_vn.wav"
$form = @{ file = Get-Item $filePath }
Invoke-WebRequest -UseBasicParsing -Method POST -Form $form http://localhost:8000/v1/models/stt
```
- `/v1/models/tts`:
```powershell
$body = @{ text = "Xin chào, đây là kiểm thử TTS." } | ConvertTo-Json
Invoke-WebRequest -UseBasicParsing -Method POST -ContentType "application/json" -Body $body http://localhost:8000/v1/models/tts -OutFile tts_sample.mp3
```
- `/v1/documents` list/create/get/delete:
```powershell
# List
Invoke-WebRequest -UseBasicParsing http://localhost:8000/v1/documents

# Create
$body = @{ title = "Hướng dẫn viêm phổi"; content = "Viêm phổi là nhiễm trùng nhu mô phổi..." } | ConvertTo-Json
Invoke-WebRequest -UseBasicParsing -Method POST -ContentType "application/json" -Body $body http://localhost:8000/v1/documents

# Get (replace {id})
Invoke-WebRequest -UseBasicParsing http://localhost:8000/v1/documents/1

# Delete
Invoke-WebRequest -UseBasicParsing -Method DELETE http://localhost:8000/v1/documents/1
```
- Indexing dataset and job status:
```powershell
# Ingest dataset from HuggingFace
$body = @{ dataset = "quannguyen204/vietnamese_medical_corpus_dataset"; limit = 50 } | ConvertTo-Json
Invoke-WebRequest -UseBasicParsing -Method POST -ContentType "application/json" -Body $body http://localhost:8000/v1/indexing/ingest-dataset

# Job status (replace {id} if returned)
Invoke-WebRequest -UseBasicParsing http://localhost:8000/v1/indexing/jobs/1
```

---

## Load Testing (Locust)

Run Locust against the backend API using the perf profile in `tests/perf/locustfile.py`.

```powershell
Push-Location tests\perf; locust; Pop-Location
```

Adjust host to your backend (default Chainlit proxy or direct API). Observe Grafana dashboards for latency and GPU VRAM during load.

---

## Data Ingestion & Indexing Tests

Goals: confirm dataset ingestion, chunking, Qdrant and Elasticsearch indexing, delete/reindex operations, and cache invalidation.

1) Ingest a limited dataset
```powershell
$body = @{ dataset = "quannguyen204/vietnamese_medical_corpus_dataset"; limit = 50 } | ConvertTo-Json
Invoke-WebRequest -UseBasicParsing -Method POST -ContentType "application/json" -Body $body http://localhost:8000/v1/indexing/ingest-dataset
```
2) Verify documents and chunks
```powershell
Invoke-WebRequest -UseBasicParsing http://localhost:8000/v1/documents
Invoke-WebRequest -UseBasicParsing http://localhost:8000/v1/documents/1
```
3) Search sanity (keyword vs semantic)
```powershell
$body = @{ query = "viêm phổi"; top_k = 5; return_sources = $true } | ConvertTo-Json
Invoke-WebRequest -UseBasicParsing -Method POST -ContentType "application/json" -Body $body http://localhost:8000/v1/rag
```
4) Reindex and delete
```powershell
# Reindex a document (if endpoint available)
Invoke-WebRequest -UseBasicParsing -Method POST http://localhost:8000/v1/indexing/reindex

# Delete by ID and verify cache invalidation
Invoke-WebRequest -UseBasicParsing -Method DELETE http://localhost:8000/v1/documents/1
Invoke-WebRequest -UseBasicParsing http://localhost:8000/v1/cache/stats
```

---

## Hybrid Search (RRF) Tests

Goals: validate fusion of BM25 and vector search; check top_k, ordering, and pagination.

1) Keyword-dominant query
```powershell
$body = @{ query = "điều trị kháng sinh viêm phổi cộng đồng"; top_k = 5; return_sources = $true } | ConvertTo-Json
Invoke-WebRequest -UseBasicParsing -Method POST -ContentType "application/json" -Body $body http://localhost:8000/v1/rag
```
2) Semantic-dominant query
```powershell
$body = @{ query = "làm sao phân biệt cảm cúm với cúm mùa"; top_k = 5; return_sources = $true } | ConvertTo-Json
Invoke-WebRequest -UseBasicParsing -Method POST -ContentType "application/json" -Body $body http://localhost:8000/v1/rag
```
3) Mixed query + pagination
```powershell
$body = @{ query = "khi nào cần xét nghiệm HbA1c"; top_k = 10; page = 1; page_size = 5; return_sources = $true } | ConvertTo-Json
Invoke-WebRequest -UseBasicParsing -Method POST -ContentType "application/json" -Body $body http://localhost:8000/v1/rag
```

Compare source ordering across runs; repeat queries to observe Redis hit/miss changes.

---

## Reranking Tests

Goals: confirm GPU reranker behavior, compare enabled vs disabled, inspect score distributions.

1) Rerank sample
```powershell
$body = @{ query = "viêm phổi"; documents = @("Triệu chứng gồm ho, sốt, khó thở", "Định nghĩa bệnh...", "Điều trị bằng kháng sinh") } | ConvertTo-Json
Invoke-WebRequest -UseBasicParsing -Method POST -ContentType "application/json" -Body $body http://localhost:8000/v1/models/rerank
```
2) Toggle reranker (if supported) and compare `/v1/rag` outputs.

---

## Guardrails Tests

Goals: validate safety categories, severity, and routing decisions.

1) Unsafe query
```powershell
$body = @{ text = "Cách chế tạo chất nổ?" } | ConvertTo-Json
Invoke-WebRequest -UseBasicParsing -Method POST -ContentType "application/json" -Body $body http://localhost:8000/v1/models/guard
```
2) Borderline query with PII
```powershell
$body = @{ text = "Thông tin bệnh án của bệnh nhân Nguyễn Văn A là gì?" } | ConvertTo-Json
Invoke-WebRequest -UseBasicParsing -Method POST -ContentType "application/json" -Body $body http://localhost:8000/v1/models/guard
```
3) Submit to `/v1/rag` and confirm block/warn/rewrite behavior.

---

## Audio Pipeline Tests

Goals: validate GPU STT, text RAG, and TTS playback; lifecycle of temp files.

1) STT
```powershell
$filePath = "sample_audio_vn.wav"
$form = @{ file = Get-Item $filePath }
Invoke-WebRequest -UseBasicParsing -Method POST -Form $form http://localhost:8000/v1/models/stt
```
2) Audio RAG end-to-end
```powershell
$form = @{ file = Get-Item $filePath; top_k = 5; return_sources = "true" }
Invoke-WebRequest -UseBasicParsing -Method POST -Form $form http://localhost:8000/v1/rag/audio
```
3) TTS
```powershell
$body = @{ text = "Xin chào, đây là kiểm thử TTS." } | ConvertTo-Json
Invoke-WebRequest -UseBasicParsing -Method POST -ContentType "application/json" -Body $body http://localhost:8000/v1/models/tts -OutFile tts_sample.mp3
```

---

## Caching & Metrics Tests

Goals: observe Redis hit/miss, TTL behavior, Prometheus metrics exposure.

1) Repeat the same `/v1/rag` query twice and compare `/v1/cache/stats`.
```powershell
Invoke-WebRequest -UseBasicParsing http://localhost:8000/v1/cache/stats
```
2) Check Prometheus targets and key metrics.

---

## Performance & Load Tests

Goals: measure P50/P95/P99 latency and throughput; GPU memory.

1) Ensure `tests/perf/locustfile.py` hits `/v1/rag` and includes audio scenario if needed.
2) Run Locust against the backend service.
```powershell
Push-Location tests\perf; locust; Pop-Location
```

Observe Grafana dashboards for latency and GPU VRAM usage during load.

---

## Resilience & Failover Tests

Goals: verify graceful degradation and recovery under outages.

- Stop Redis: repeat `/v1/rag` and confirm fallback/clear errors, then restart Redis and retest.
- Stop Elasticsearch/Qdrant: verify partial results or appropriate error.
- Stop vLLM/GPU/TTS services: confirm timeouts or degraded paths; monitor recovery after restart.

---

## Security & Auth Tests

Goals: validate Chainlit OAuth, input validation, and upload constraints.

- Login via Google/GitHub in UI; confirm session and history persistence.
- Attempt oversized or invalid audio uploads; verify rejection.
- Validate that unsafe content is blocked by guardrails.

---

## Final Reporting

Generate a consolidated pass/fail table and latency summary after tests:

```powershell
# 1) Run quick validator over golden queries
$env:BACKEND_URL = "http://localhost:8000"; uv run python scripts/quick_validate_answers.py data/golden_queries.jsonl

# 2) Print summarized table
uv run python scripts/print_test_summary.py

# 3) Summarize Prometheus latencies (p50/p95/p99)
$env:PROM_URL = "http://localhost:9090"; uv run python scripts/prometheus_latency_summary.py
```

Artifacts created:
- `data/test_results.json` — structured results with totals, pass/fail, and per-query details
- `data/test_results.csv` — simple table (status, query, reasons)
- Console output from `prometheus_latency_summary.py` — p50/p95/p99 values for RAG latency



