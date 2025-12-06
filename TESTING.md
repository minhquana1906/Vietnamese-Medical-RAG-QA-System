# Test Execution Guide (GPU + Small Samples)

This guide describes how to run full GPU-enabled services and execute small, real end-to-end samples through the Chainlit app to validate all features: text RAG, audio pipeline, hybrid search, reranking, guardrails, caching, and monitoring.

## Prerequisites

- NVIDIA GPU with recent drivers and CUDA support (Docker Desktop GPU enabled or Linux host)
- Docker Desktop (Windows) or Docker Engine (Linux) with Compose V2
- Verified API keys: `HF_TOKEN`, `ELEVENLABS_API_KEY`, optionally `OPENAI_API_KEY`, `TAVILY_API_KEY`
- `.env` file created from `.env.example`

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

Ports in use:
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
- Documents appear in Chainlit UI or via `/v1/documents` list
- Chunks visible and searchable
- Qdrant/Elasticsearch logs show inserts

## Text RAG Samples

Use 3–5 Vietnamese medical queries in the Chainlit chat, e.g.:
- "Triệu chứng điển hình của viêm phổi là gì?"
- "Thuốc hạ sốt nào an toàn cho trẻ em?"
- "Khi nào cần xét nghiệm HbA1c cho bệnh nhân tiểu đường?"

Check:
- Citations (document sources)
- Faithfulness and relevancy of answers
- Latency (UI and Prometheus metrics)

## Hybrid Search Variants

Run keyword-heavy vs semantic-heavy queries and confirm diverse top-K results via RRF fusion. Repeat a query to observe Redis cache hits in `/v1/cache/stats`.

## Reranking Checks

- Ensure reranker is enabled in config
- Compare responses with reranker off (temporary toggle if supported)
- Call `/v1/models/rerank` with a query and candidate docs to inspect score distribution

## Guardrails Tests

Submit unsafe/borderline queries and verify behavior:
- Violent/sexual/PII/jailbreak examples
- Confirm block/warn/rewrite per threshold and categories returned by `/v1/models/guard`

## Audio Pipeline (GPU STT + TTS)

In Chainlit, record a short Vietnamese question and send.
Validate:
- STT transcript accuracy
- Text answer produced via RAG
- TTS playback works; audio file accessible via UI (cleanup of temp files)

## Observability Checks

- Prometheus: `http://localhost:9090` — scrape targets include backend and GPU service
- Grafana: `http://localhost:3000` — dashboards for model latency, cache, voice pipeline, GPU VRAM
- Loki logs and Tempo traces if enabled

## Minimal External Usage

- Use one ElevenLabs TTS sample to confirm API key configured
- Trigger one Tavily routing case (if enabled) and ensure graceful behavior

## Troubleshooting

- If GPU services fail, verify Docker Desktop GPU support or run on Linux host
- Switch to CPU fallback: set `QWEN3_MODELS_ENABLED=false` in `.env` and restart backend
- Check environment variables and container logs for vLLM and GPU service readiness

## Next Steps

- Run performance tests via `testing/locustfile.py` after updating endpoints to `/v1/rag`
- Expand dataset after stability confirmed
// CI integration intentionally excluded from testing scope per requirements.

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

1) Update `testing/locustfile.py` to hit `/v1/rag` and add an audio scenario.
2) Run Locust against the backend service.
```powershell
Push-Location "testing"; locust; Pop-Location
```

Observe Grafana dashboards for latency and GPU VRAM usage during load.

---

## Resilience & Failover Tests

Goals: verify graceful degradation and recovery under outages.

- Stop Redis: repeat `/v1/rag` and confirm fallback/clear errors, then restart Redis and retest.
- Stop Elasticsearch/Qdrant: verify partial results or error surfaced appropriately.
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



