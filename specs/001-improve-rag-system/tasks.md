# Tasks: RAG System Comprehensive Improvements

**Feature Branch**: `001-improve-rag-system`
**Created**: 2025-10-31
**Updated**: 2025-11-19 (Serving Architecture Refactoring + RAG Evaluation)
**Input**: Design documents from `/specs/001-improve-rag-system/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Tests are NOT REQUIRED during MVP phase per constitution. Tasks focus on working functionality.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

> **� Architecture Update (2025-11-19)**:
> - ✅ **Serving Refactored**: Triton replaced with FastAPI for embedding/reranking/guardrails
> - ✅ **Model Serving**: Remote vLLM for generation, Local FastAPI for embedding/reranking/guardrails
> - ✅ **Fine-tuning Removed**: Tasks T049-T078 removed (out of current scope)
> - ✅ **Triton Removed**: Tasks T005, T009, T069-T072 removed (replaced by FastAPI)
> - 🆕 **RAG Evaluation Added**: New Phase 4 with comprehensive metrics (Recall@K, nDCG@K, MRR, Faithfulness, Answer Relevance, Correctness, Latency)
> - 🆕 **Evaluation Tools**: DeepEval + LlamaIndex for automated RAG assessment

> **📝 Previous Updates**: 
> - ✅ Schema Simplification (2025-11-01): Chainlit standard schema + OAuth only
> - ✅ Phase 2 (Foundational) completed: T015-T030d (database schema, migration, legacy cleanup)
> - ✅ Phase 3 (User Story 1) completed: T031-T048 (Chainlit UI with OAuth)

## Format: `- [ ] [ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and new infrastructure setup

- [X] T001 Create new directory structure per plan.md (serving/, monitoring/, testing/, frontend/components/)
- [X] T002 [P] Update backend/docker-compose.yml to include Elasticsearch 8.11.0 service
- [X] T003 [P] Create monitoring/docker-compose.yml for Prometheus, Loki, Tempo, Promtail, Grafana
- [X] T004 [P] Create serving/vllm/docker-compose.yml for remote vLLM generation model serving
- [X] T006 [P] Create .env.example with all required environment variables (HF_TOKEN, WANDB_API_KEY, etc.)
- [X] T007 [P] Update backend/requirements.txt with new dependencies (chainlit, elasticsearch, prometheus-client, opentelemetry-api)
- [X] T010 [P] Create monitoring/grafana/dashboards/ directory with placeholder files
- [X] T011 [P] Create monitoring/prometheus.yml configuration
- [X] T012 [P] Create monitoring/loki/loki-config.yaml configuration
- [X] T013 [P] Create monitoring/tempo/tempo-config.yaml configuration
- [X] T014 [P] Create testing/locustfile.py skeleton for load testing

**Note**: Tasks T005 (Triton), T008 (ml/requirements.txt), T009 (Triton models) removed - replaced by FastAPI serving

**Git Example**: `git commit -m "Add infrastructure configuration for monitoring and model serving"`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T015 Create Alembic migration for Chainlit schema in backend/alembic/versions/XXXX_chainlit_schema.py
- [X] T016 Update backend/src/models.py with User, ChatSession, Message, FineTunedModel entities per data-model.md
- [X] T017 [P] Create backend/src/schemas/chainlit_schema.py with Pydantic schemas for Chainlit entities
- [X] T018 [P] Update backend/src/database.py with connection settings for new schema
- [X] T019 Implement Redis cache wrapper in backend/src/core/cache.py with get_query_embedding, cache_query_embedding, get_search_results, cache_search_results methods
- [X] T020 [P] Create Elasticsearch client wrapper in backend/src/services/elasticsearch.py with index_chunk, search_bm25 methods
- [X] T021 [P] Implement Qwen3 embedding service in backend/src/services/embedding.py with embed_text, embed_batch methods
- [X] T022 [P] Create hybrid search implementation in backend/src/core/hybrid_search.py with rrf_fusion function
- [X] T023 [P] Update backend/src/services/brain.py to support Qwen3 model integration with vLLM fallback
- [X] T024 [P] Update backend/src/services/rerank.py to use Qwen3-Reranker with Cohere fallback
- [X] T025 [P] Create guardrails service in backend/src/core/guardrails.py for Qwen3Guard integration
- [X] T026 [P] Add Prometheus metrics instrumentation in backend/src/main.py (counters, histograms for RAG pipeline stages)
- [X] T027 [P] Add OpenTelemetry tracing setup in backend/src/main.py for distributed tracing
- [X] T028 [P] Configure Loguru with JSON formatter in backend/src/configs/logging_config.py
- [X] T029 Create backend/scripts/migrate_conversations.py for migrating old conversation data to Chainlit schema
- [X] T030 Run Alembic migration to create new database schema: `alembic upgrade head` (requires database to be running)
- [X] T030a Execute backend/scripts/drop_legacy_data.py to drop legacy chat_conversations table (database contains only test data, no migration needed): `python -m backend.scripts.drop_legacy_data`
- [X] T030c Remove legacy code from backend/src/models.py (ChatConversation class and related functions: get_conversation_by_id, update_conversation, convert_conversation_to_messages, get_messages_from_conversation) - see backend/scripts/LEGACY_CODE_REMOVAL_GUIDE.md
- [X] T030d Update backend/src/tasks.py to use new Thread/Step models (Chainlit schema) instead of legacy ChatSession/Message - COMPLETED 2025-11-01: message_handler_task now uses user_identifier, thread_id, and Chainlit schema; legacy /chat/complete endpoint updated for backward compatibility
- [X] T030b [P] Add health check endpoints in backend/src/main.py: GET /health (API status), GET /health/db (database connectivity), GET /health/cache (Redis connectivity)

**Git Example**: `git commit -m "Implement core authentication and database schema for user management"`

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Modern Chat Interface with OAuth Authentication (Priority: P1) 🎯 MVP

**Goal**: Users can interact with the medical RAG system through a Chainlit UI with OAuth authentication and persistent sessions

**Independent Test**: Login with Google/GitHub, ask medical questions, logout, login again and verify conversation history is preserved

**Context**: Database now uses Chainlit standard schema (users, threads, steps, elements, feedbacks). OAuth-only authentication via Chainlit (no passwords, no JWT). Session management handled by Chainlit internally.

**✅ Prerequisites Complete (2025-11-01)**:

- Backend now uses Chainlit schema (Thread, Step, User models)
- message_handler_task refactored to accept (user_identifier, thread_id, query)
- Legacy /chat/complete endpoint updated for backward compatibility
- Ready to proceed with Chainlit frontend implementation (T031-T048)

### Implementation for User Story 1

- [X] T031 [P] [US1] Configure OAuth in frontend/.chainlit/config.toml with Google and GitHub provider settings (client_id, client_secret, redirect_uri) - COMPLETED 2025-11-01
- [X] T032 [P] [US1] Chainlit configuration integrated in config.toml (database URL, session settings) - COMPLETED 2025-11-01
- [X] T033 [US1] Configure Chainlit data layer in frontend/chainlit.py using @cl.data_layer decorator with SQLAlchemy connection - COMPLETED 2025-11-02
- [X] T034 [P] [US1] OAuth configured in config.toml for Google provider - COMPLETED 2025-11-01
- [X] T035 [P] [US1] OAuth configured in config.toml for GitHub provider - COMPLETED 2025-11-01
- [X] T036 [US1] Create main Chainlit app in frontend/chainlit.py with @cl.on_chat_swwwwwwwwtart decorator (initialize thread, load history) - COMPLETED 2025-11-01
- [X] T037 [US1] Implement message handler in frontend/chainlit.py with @cl.on_message decorator (calls backend API POST /rag/query) - COMPLETED 2025-11-01
- [X] T038 [P] [US1] Configure Chainlit authentication in frontend/.chainlit/config.toml to enable OAuth providers and disable password auth - COMPLETED 2025-11-01
- [X] T039 [US1] Thread management implemented in frontend/chainlit.py: create threads via backend API - COMPLETED 2025-11-01
- [X] T040 [P] [US1] Implement thread UI components in frontend/chainlit.py: thread list sidebar, thread switching, thread history display - COMPLETED 2025-11-02 (Chainlit provides this automatically via data layer)
- [X] T041 [US1] RAG pipeline integrated in frontend/chainlit.py: calls backend POST /rag/query with user_identifier, thread_id, query - COMPLETED 2025-11-01
- [X] T042 [P] [US1] Add streaming response support in frontend/chainlit.py using cl.Message with streaming=True - COMPLETED 2025-11-02
- [X] T043 [P] [US1] Frontend components/ directory exists (empty, ready for custom components) - COMPLETED
- [X] T044 [P] [US1] Frontend public/ directory exists with logo.png - COMPLETED
- [X] T045 [US1] Update backend/src/tasks.py with rag_pipeline_task Celery task for async RAG processing (called from Chainlit) - COMPLETED 2025-11-02 (Already implemented as message_handler_task)
- [X] T046 [US1] Backend API endpoint POST /rag/query created in backend/src/main.py (calls message_handler_task) - COMPLETED 2025-11-01
- [X] T046a [US1] Refactor backend API với modular router structure (health, rag, models, audio, documents routers) - COMPLETED 2025-11-24
- [X] T047 [US1] Frontend Dockerfile created for Chainlit container - COMPLETED 2025-11-01
- [X] T048 [US1] Frontend docker-compose.yml created with Chainlit + PostgreSQL - COMPLETED 2025-11-01

**Git Example**: `git commit -m "Add Chainlit UI with OAuth authentication for Google and GitHub providers"`

**Checkpoint**: At this point, User Story 1 should be fully functional - users can authenticate, create sessions, and chat

---

## Phase 4: Model Serving Configuration (Priority: P2)

**Goal**: Configure and verify model serving infrastructure with FastAPI backend and remote vLLM

**Independent Test**: Verify all models (embedding, reranking, guardrails via FastAPI; generation via remote vLLM) are accessible and working correctly

**Context**: Fine-tuning tasks removed from scope. Focus on configuring existing models for optimal serving.

### Implementation for Model Serving

- [X] T068 [P] [US2] Create serving/vllm/entrypoint.sh script to start remote vLLM with generation model
- [X] T073 [US2] Create backend/config/models.yaml for model configuration management
- [X] T074 [P] [US2] Create backend/src/core/model_config.py for loading model config from YAML
- [X] T075 [P] [US2] Update backend/src/services/brain.py to read generation model from config file and use remote vLLM
- [X] T076 [US2] Update backend/src/services/embedding.py to use FastAPI backend for embedding service
- [X] T077 [US2] Update backend/src/services/rerank.py to use FastAPI backend for reranking service
- [X] T078 [US2] Remove database-based model management (FineTunedModel table, API endpoints, schemas)
- [X] T078c [US2] Integrate guardrails validation into backend/src/core/guardrails.py with logging for filtered queries
- [X] T078d [US2] Update backend/src/tasks.py to use Qwen3 models (embedding, reranking, generation) with proper error handling
- [X] T078e [US2] Update RAG pipeline helper functions (enhance_query_quality, detect_route, get_tavily_agent_answer) to use Qwen3


**Note**: Fine-tuning tasks (T049-T067, T069-T072) removed - replaced by pre-trained model serving via FastAPI

**Git Example**: `git commit -m "Configure model serving with FastAPI backend and remote vLLM"`

**Checkpoint**: At this point, all models are properly configured and serving via FastAPI/vLLM

---

## Phase 5: User Story 3 - Improved Retrieval through Hybrid Search (Priority: P3)

**Goal**: System combines semantic vector search with keyword-based search using RRF to retrieve more relevant documents

**Independent Test**: Run benchmark queries and compare retrieval metrics (precision, recall, MRR) between pure vector and hybrid RRF approach

### Implementation for User Story 3

- [X] T079 [P] [US3] Implement BM25 keyword search in backend/src/services/elasticsearch.py with Vietnamese text analyzer
- [X] T080 [P] [US3] Implement vector search wrapper in backend/src/core/vectorize.py for Qdrant similarity search
- [X] T081 [US3] Implement Reciprocal Rank Fusion in backend/src/core/hybrid_search.py with configurable k parameter (default k=60)
- [X] T082 [US3] Create hybrid_search function that combines vector and keyword results in backend/src/core/hybrid_search.py
- [X] T083 [US3] Update backend/src/tasks.py message_handler_task to use hybrid search instead of vector-only search
- [X] T084 [P] [US3] Add search type metrics to Prometheus instrumentation (rag_search_requests_total{search_type="vector|keyword|hybrid"})
- [X] T085 [P] [US3] Update caching layer in backend/src/core/cache.py to cache hybrid search results with key prefix "search:hybrid:"
- [X] T086 [US3] Configure Elasticsearch index mapping in database/init.sql with Vietnamese analyzer settings
- [X] T087 [US3] Update document chunking in backend/src/services/chunking.py to implement **single fixed semantic strategy** across all document types with sentence boundary awareness (512 token limit, 50 token overlap)
- [X] T088 [US3] Update chunk indexing to write to both Qdrant and Elasticsearch in backend/src/tasks.py

**Git Example**: `git commit -m "Implement hybrid search with RRF fusion showing 18% improvement in precision@10"`

**Checkpoint**: At this point, hybrid search is operational and showing improved retrieval quality

---

## Phase 6: User Story 4 - Optimized Dataset Integration (Priority: P4)

**Goal**: System loads and indexes comprehensive Vietnamese medical dataset with improved metadata and efficient chunk management

**Independent Test**: Load dataset, verify metadata completeness, run sample queries to ensure chunks are retrieved with proper context

### Implementation for User Story 4

- [X] T089 [P] [US4] Implement document ingestion endpoint in backend/src/main.py: POST /indexing/ingest-dataset per documents-api.yaml
- [X] T090 [P] [US4] Implement job status endpoint in backend/src/main.py: GET /indexing/jobs/{job_id} per documents-api.yaml
- [X] T091 [P] [US4] Implement document management endpoints in backend/src/main.py: GET /documents, POST /documents, GET /documents/{document_id}, DELETE /documents/{document_id} per documents-api.yaml
- [X] T092 [P] [US4] Implement reindex endpoint in backend/src/main.py: POST /indexing/reindex-document/{document_id} per documents-api.yaml
- [X] T093 [US4] Create chunk_and_index_document Celery task in backend/src/tasks.py for async document processing
- [X] T094 [US4] Enhance chunking strategy in backend/src/services/chunking.py with improved semantic awareness (respect sentence boundaries, 512 token limit, 50 token overlap)
- [X] T095 [US4] Update chunk metadata in backend/src/models.py to include source_document_id, chunk_index, section_title, page_number
- [X] T096 [US4] Implement batch embedding generation in backend/src/services/embedding.py for efficient processing
- [X] T097 [US4] Update Qdrant insertion in backend/src/core/vectorize.py to include enhanced metadata in payload
- [X] T098 [US4] Update Elasticsearch indexing in backend/src/services/elasticsearch.py with full metadata fields
- [X] T099 [US4] Implement progress tracking in chunk_and_index_document task using Celery task.update_state
- [X] T100 [US4] Run backend/scripts/load_dataset.py to download quannguyen204/vietnamese_medical_corpus_dataset from HuggingFace (https://huggingface.co/datasets/quannguyen204/vietnamese_medical_corpus_dataset)
- [X] T101 [US4] Execute POST /indexing/ingest-dataset to index vietnamese_medical_corpus_dataset into Qdrant and Elasticsearch
- [X] T102 [US4] Verify all documents indexed successfully with metadata completeness check
- [X] T102a [P] [US4] Implement incremental dataset update logic in backend/src/tasks.py to handle document updates without full reindex (check document hash, update only changed documents)
- [X] T102b [P] [US4] Add dataset version tracking in backend/src/models.py to support incremental updates per FR-026

**Git Example**: `git commit -m "Add dataset ingestion pipeline with enhanced metadata tracking and chunk management"`

**Checkpoint**: At this point, complete medical dataset is indexed with proper metadata and chunks

---

## Phase 7: User Story 5 - Performance Optimization through Caching (Priority: P5)

**Goal**: System implements caching layer for embeddings and search results to reduce latency and computational costs

**Independent Test**: Issue identical queries and measure response time reduction on cache hits vs cache misses

### Implementation for User Story 5

- [X] T103 [P] [US5] Implement embedding caching in backend/src/services/embedding.py (check cache before generating, cache after generation)
- [X] T104 [P] [US5] Implement search result caching in backend/src/core/hybrid_search.py (cache final RRF results)
- [X] T105 [US5] Add cache hit/miss metrics in backend/src/core/cache.py with Prometheus counters (cache_hits_total{cache_type="embedding|search"})
- [X] T106 [US5] Implement cache invalidation on document deletion in backend/src/main.py DELETE /documents/{document_id} endpoint
- [X] T106a [US5] Implement cache invalidation on document update in backend/src/main.py PATCH /documents/{document_id} endpoint (clear search caches for affected document) - SKIPPED: No update endpoint exists
- [X] T107 [US5] Configure Redis LRU eviction policy in database/docker-compose.yml (maxmemory-policy allkeys-lru)
- [X] T108 [US5] Add cache warming script in backend/scripts/warm_cache.py for common medical queries
- [X] T109 [US5] Update backend/src/tasks.py to use cached embeddings in message_handler_task
- [X] T110 [US5] Add cache statistics endpoint in backend/src/main.py: GET /cache/stats (hit rate, entry count, memory usage)

**Git Example**: `git commit -m "Add Redis caching layer with 42% cache hit rate on common queries"`

**Checkpoint**: At this point, caching is operational and showing reduced latency for repeated queries

---

## Phase 8: User Story 6 - Minimal MVP Monitoring (Priority: P6)

**Goal**: Essential observability với full model metrics (generation/embedding/rerank/guardrails) + voice pipeline monitoring

**Independent Test**: Trigger RAG + voice operations, verify all model metrics visible in Grafana

### Implementation for User Story 6 (MVP Scope)

**Infrastructure Setup**:
- [X] T111-T121 [US6] Basic monitoring stack configured (Prometheus, Loki, Tempo, Grafana)
- [X] T122 [US6] Fix Prometheus config: Add GPU service scrape target in monitoring/prometheus/prometheus.yml
- [X] T123 [US6] Fix Promtail config: Enable Docker auto-discovery in monitoring/promtail/promtail-config.yaml
- [X] T124 [US6] Update monitoring docker-compose: Ensure Docker socket mount for Promtail

**GPU Service Instrumentation**:
- [X] T125 [US6] Add prometheus-client to serving/qwen3_models/requirements.txt
- [X] T126 [US6] Add /metrics endpoint in serving/qwen3_models/app.py (Prometheus exporter)
- [X] T127 [US6] Instrument 4 model endpoints: /embed, /rerank, /guard, /stt với latency + count metrics
- [X] T128 [US6] Add GPU memory tracking với background task (update every 30s)
- [X] T129 [US6] Restart GPU service: `cd serving/qwen3_models && docker compose restart`

**Voice Pipeline Instrumentation**:
- [X] T130 [US6] Add voice metrics in backend/src/core/metrics.py (3 metrics: duration, stage_duration, errors)
- [X] T131 [US6] Instrument /v1/models/stt, /v1/models/tts, /v1/rag/audio in backend/src/routers/audio.py

**RAG Pipeline Tracing**:
- [X] T132 [US6] Add OpenTelemetry tracer to backend/src/tasks.py
- [X] T133 [US6] Create tracing utilities in backend/src/core/tracing.py
- [X] T134 [US6] Add tracing to RAG router endpoint in backend/src/routers/rag.py (wraps RAG service)
- [X] T135 [US6] Restart backend: `cd backend && docker compose restart chatbot_api`

**Dashboards**:
- [X] T136 [US6] Create dashboards provisioning config: monitoring/grafana/dashboards/dashboards.yaml
- [X] T137 [US6] Build custom Model Monitoring dashboard: monitoring/grafana/dashboards/model_monitoring.json (7 panels)
- [X] T138 [US6] Restart Grafana to import dashboards: `cd monitoring && docker compose restart grafana`

**Alerts**:
- [X] T139 [US6] Update monitoring/prometheus/alerts.yml with 2 new rules (HighModelInferenceLatency, HighVoiceErrorRate)
- [X] T140 [US6] Reload Prometheus: `curl -X POST http://localhost:9090/-/reload`

**Verification**:
- [X] T141 [US6] Verify GPU metrics: `curl http://localhost:8002/metrics | grep model_inference`
- [X] T142 [US6] Verify voice metrics: `curl http://localhost:8000/metrics | grep voice_`
- [X] T143 [US6] Verify logs: Grafana Explore → Loki → `{job="docker_containers"}`
- [ ] T144 [US6] Verify RAG traces: Grafana Explore → Tempo → Service: chatbot_api
- [X] T145 [US6] Verify Model Monitoring dashboard showing data in all 7 panels

**Git Example**: `git commit -m "Add minimal MVP monitoring with full model metrics + voice pipeline observability"`

**Checkpoint**: Essential monitoring operational, đủ visibility để debug model performance issues

---

## Phase 9: User Story 7 - Performance Testing and Validation (Priority: P7)

**Goal**: System undergoes stress and load testing to validate performance characteristics and identify bottlenecks

**Independent Test**: Run load tests with 100 concurrent users and measure system behavior (throughput, latency, error rates)

### Implementation for User Story 7

- [ ] T127 [P] [US7] Create testing/locustfile.py with RAGUser class and realistic query scenarios
- [ ] T128 [P] [US7] Create testing/stress_test.py with gradual load increase from 10 to 500 users
- [ ] T129 [P] [US7] Create testing/results/ directory for storing test output
- [ ] T130 [US7] Implement load test scenarios in testing/locustfile.py: simple_query task (weight 3), complex_query task (weight 1)
- [ ] T131 [P] [US7] Add spike test scenario in testing/locustfile.py for sudden load increase
- [ ] T132 [US7] Run load test with 100 concurrent users, 10 users/second spawn rate for 10 minutes
- [ ] T133 [US7] Collect and analyze metrics from Grafana during load test (p50, p95, p99 latencies)
- [ ] T134 [US7] Run stress test with gradually increasing load to find system breaking point
- [ ] T135 [US7] Identify bottlenecks from Prometheus metrics (CPU, memory, GPU, external API limits)
- [ ] T136 [US7] Run sustained load test for 1 hour to check for memory leaks and stability
- [ ] T137 [US7] Document performance characteristics in testing/results/performance_report.md
- [ ] T138 [US7] Verify p95 latency stays under 5 seconds with 100 concurrent users
- [ ] T139 [US7] Verify error rate stays below 1% under sustained load
- [ ] T140 [US7] Verify cache hit rate reaches at least 30% after warm-up period

**Git Example**: `git commit -m "Complete load testing validation with 100 concurrent users at p95 latency of 3.8 seconds"`

**Checkpoint**: At this point, system performance is validated and documented under realistic load

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: Final improvements that affect multiple user stories

- [ ] T141 [P] Create comprehensive setup guide in docs/setup_instructions.md with prerequisites and step-by-step installation
- [ ] T142 [P] Update README.md with feature overview, architecture diagram, and quickstart links
- [ ] T143 [P] Add API documentation in docs/api_reference.md based on OpenAPI contracts
- [ ] T144 Code cleanup and refactoring: mark legacy Streamlit code in frontend/main.py and frontend/helper.py with "# LEGACY CODE - replaced by frontend/chainlit.py" comments
- [ ] T145 [P] Add security hardening: rate limiting in backend/src/main.py using slowapi
- [ ] T146 [P] Add input validation for all API endpoints using Pydantic validators
- [ ] T146a [P] Add CORS configuration in backend/src/main.py to allow Chainlit frontend origin
- [ ] T147 [P] Create docker-compose.yml in project root to orchestrate all services (backend, frontend, databases, monitoring, serving)
- [ ] T148 [P] Create .dockerignore files to optimize Docker build context
- [ ] T148a [P] Add environment variable validation in backend/src/configs/setup.py to ensure all required vars are set at startup
- [ ] T149 Performance optimization: tune vLLM gpu-memory-utilization and max-model-len parameters
- [ ] T150 [P] Add error handling for model serving failures with graceful fallback to OpenAI/Cohere
- [ ] T151 [P] Add database connection pooling optimization in backend/src/database.py
- [ ] T152 Run quickstart.md validation end-to-end
- [ ] T153 Create deployment guide in docs/deployment.md for production setup
- [ ] T154 [P] Add troubleshooting section to docs/ for common issues

**Note**: Task T150 (Triton batching optimization) removed - replaced by FastAPI serving

**Git Example**: `git commit -m "Add comprehensive documentation and production deployment guides"`

---

## Phase 10: RAG Pipeline Evaluation (Priority: P8) 🎯 Quality Assurance

**Goal**: Comprehensively evaluate RAG pipeline performance using industry-standard metrics and automated evaluation frameworks

**Independent Test**: Run evaluation suite on test dataset and verify metrics meet quality thresholds

**Context**: Use DeepEval and LlamaIndex for automated RAG evaluation with comprehensive metrics covering retrieval quality, generation quality, and system performance.

### Implementation for RAG Evaluation

- [ ] T156 [P] [US8] Install evaluation dependencies in backend/requirements.txt (deepeval, llama-index, ragas)
- [ ] T157 [P] [US8] Create evaluation test dataset in backend/data/eval_dataset.jsonl with 100+ Vietnamese medical QA pairs (question, expected_answer, ground_truth_contexts)
- [ ] T158 [P] [US8] Create backend/scripts/evaluate_rag.py as main evaluation script with CLI arguments (--dataset, --output, --metrics)
- [ ] T159 [US8] Implement retrieval metrics evaluation in backend/scripts/evaluate_rag.py:
  - Recall@K (K=1,3,5,10): Measure if ground truth documents appear in top-K results
  - nDCG@K (K=1,3,5,10): Normalized Discounted Cumulative Gain for ranking quality
  - MRR (Mean Reciprocal Rank): Average reciprocal rank of first relevant document
  - Precision@K (K=1,3,5,10): Proportion of relevant documents in top-K
- [ ] T160 [US8] Implement generation quality metrics using DeepEval in backend/scripts/evaluate_rag.py:
  - Faithfulness: Check if generated answer is faithful to retrieved contexts (no hallucination)
  - Answer Relevance: Measure if answer is relevant to the question
  - Contextual Relevance: Measure if retrieved contexts are relevant to the question
  - Correctness: Compare generated answer vs ground truth using LLM-as-judge
- [ ] T161 [US8] Implement performance metrics in backend/scripts/evaluate_rag.py:
  - End-to-end latency (ms): Total time from query to response
  - Embedding latency (ms): Time for query embedding generation
  - Retrieval latency (ms): Time for vector + keyword search
  - Reranking latency (ms): Time for reranking results
  - Generation latency (ms): Time for LLM response generation
  - Token usage: Total tokens consumed (input + output)
- [ ] T162 [P] [US8] Create backend/scripts/eval_utils.py with helper functions:
  - compute_retrieval_metrics(predictions, ground_truths, k_values)
  - compute_generation_metrics(predictions, ground_truths, contexts)
  - compute_performance_metrics(timestamps, token_counts)
  - format_eval_report(metrics_dict) -> markdown table
- [ ] T163 [US8] Integrate LlamaIndex evaluators in backend/scripts/evaluate_rag.py:
  - RelevancyEvaluator: Question-answer relevance
  - FaithfulnessEvaluator: Answer-context faithfulness
  - CorrectnessEvaluator: Answer correctness with ground truth
- [ ] T164 [US8] Integrate DeepEval metrics in backend/scripts/evaluate_rag.py:
  - AnswerRelevancyMetric: Semantic relevance of answer to question
  - FaithfulnessMetric: Verify no hallucinations in answer
  - ContextualRelevancyMetric: Retrieved contexts relevance
  - GEval (custom criteria): Custom Vietnamese medical domain criteria
- [ ] T165 [P] [US8] Create backend/scripts/generate_eval_report.py to generate comprehensive HTML report with:
  - Summary table with all metrics
  - Per-query breakdown with failures highlighted
  - Visualizations (latency distribution, score histograms)
  - Failure analysis with examples
- [ ] T166 [US8] Create evaluation configuration in backend/config/eval_config.yaml:
  - Metric thresholds (min_recall@5=0.7, min_faithfulness=0.8, max_latency_p95=5000ms)
  - LLM judge configuration (model, temperature, prompt templates)
  - Dataset paths and output directories
- [ ] T167 [US8] Run full evaluation suite: `python backend/scripts/evaluate_rag.py --dataset data/eval_dataset.jsonl --output data/eval_results/`
- [ ] T168 [US8] Verify metrics meet quality thresholds:
  - Retrieval: Recall@5 >= 0.70, nDCG@5 >= 0.65, MRR >= 0.60
  - Generation: Faithfulness >= 0.80, Answer Relevance >= 0.75, Correctness >= 0.70
  - Performance: p95 latency <= 5000ms, p50 latency <= 3000ms
- [ ] T169 [P] [US8] Create automated evaluation CI workflow in .github/workflows/rag-eval.yml to run on PR
- [ ] T170 [P] [US8] Document evaluation methodology in docs/RAG_EVALUATION.md with metric definitions and interpretation guide

**Evaluation Tools Reference**:
- **DeepEval**: https://docs.confident-ai.com/ (LLM evaluation framework)
- **LlamaIndex**: https://docs.llamaindex.ai/en/stable/module_guides/evaluating/ (RAG evaluation)
- **RAGAS**: https://docs.ragas.io/ (RAG assessment framework)

**Git Example**: `git commit -m "Add comprehensive RAG evaluation with retrieval, generation, and performance metrics"`

**Checkpoint**: At this point, RAG pipeline quality is measured and validated against industry standards

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-9)**: All depend on Foundational phase completion
  - User stories can then proceed in parallel (if staffed)
  - Or sequentially in priority order (P1 → P2 → P3 → P4 → P5 → P6 → P7)
- **Polish (Phase 10)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **Model Serving (P2)**: Can start after Foundational (Phase 2) - Configures FastAPI + vLLM serving
- **User Story 3 (P3)**: Can start after Foundational (Phase 2) - Uses models from Phase 4 but can use baseline
- **User Story 4 (P4)**: Can start after Foundational (Phase 2) - Uses chunking/embedding but independently testable
- **User Story 5 (P5)**: Depends on US3/US4 for caching search results - but independently testable
- **User Story 6 (P6)**: Can start after Foundational (Phase 2) - Monitors all stories but independently deployable
- **User Story 7 (P7)**: Should run after US1-US6 complete - tests all previous stories under load
- **RAG Evaluation (P8)**: Can start after US3/US4 complete - requires working retrieval + generation pipeline

### Within Each Phase

- Tasks marked [P] can run in parallel (different files, no conflicts)
- Non-[P] tasks should run sequentially within the phase
- Complete all tasks in a phase before moving to next phase

### Parallel Opportunities

#### Phase 1 (Setup)

```bash
# All tasks marked [P] can run in parallel:
T002, T003, T004, T006, T007, T010, T011, T012, T013, T014
```

#### Phase 2 (Foundational)

```bash
# After T015-T018 complete, these can run in parallel:
T019, T020, T021, T022, T023, T024, T025, T026, T027, T028
```

#### User Story 1 (Phase 3)

```bash
# These can run in parallel:
T031, T032, T034, T035, T037, T038, T040, T042, T043, T044
```

#### Model Serving (Phase 4)

```bash
# Model serving configs can run in parallel:
T074, T075, T076, T078f, T078h
```

#### Multiple User Stories in Parallel

If you have multiple team members, after Foundational phase completes:

- Team Member A: User Story 1 (T031-T048) - Chainlit UI
- Team Member B: Model Serving (T068-T078h) - FastAPI serving configuration
- Team Member C: User Stories 3 & 4 (T079-T102b) - Hybrid Search & Dataset
- Team Member D: User Story 6 (T111-T126) - Monitoring Stack
- Team Member E: RAG Evaluation (T156-T170) - Quality metrics

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T014)
2. Complete Phase 2: Foundational (T015-T030) - CRITICAL checkpoint
3. Complete Phase 3: User Story 1 (T031-T048)
4. **STOP and VALIDATE**: Test authentication, chat sessions, conversation history
5. Deploy/demo Chainlit UI with working chat

**MVP Delivers**: Working chat interface with authentication and persistent sessions

### Incremental Delivery

1. **Foundation** (Setup + Foundational) → Core infrastructure ready
2. **Release 1**: Add User Story 1 → Test → Deploy → **Users can chat with RAG system**
3. **Release 2**: Add Model Serving Config → Test → Deploy → **Models properly configured and serving**
4. **Release 3**: Add User Story 3 → Test → Deploy → **Users get better document retrieval via hybrid search**
5. **Release 4**: Add User Story 4 → Test → Deploy → **System has full medical dataset indexed**
6. **Release 5**: Add User Story 5 → Test → Deploy → **Users experience faster responses via caching**
7. **Release 6**: Add User Story 6 → Test → Deploy → **Team has full observability**
8. **Release 7**: Add User Story 7 → Test → Deploy → **System validated for production load**
9. **Release 8**: Add RAG Evaluation → Test → Deploy → **Pipeline quality measured and validated**

Each release adds value without breaking previous functionality.

### Parallel Team Strategy

With 5 developers after Foundational phase completes:

- **Developer A**: User Story 1 (Authentication & Chainlit UI)
- **Developer B**: Model Serving Configuration (FastAPI + vLLM)
- **Developer C**: User Stories 3 & 4 (Hybrid Search & Dataset Integration)
- **Developer D**: User Story 6 (Monitoring Stack)
- **Developer E**: RAG Evaluation Framework (Quality Metrics)

Then collectively complete User Stories 5 and 7.

---

## Task Summary

- **Total Tasks**: 170 (updated with serving refactor and RAG evaluation)
- **Phase 1 (Setup)**: 11 tasks (removed Triton T005, T008, T009)
- **Phase 2 (Foundational)**: 18 tasks (completed - database schema, migration, legacy cleanup)
- **Phase 3 (US1 - Chainlit UI)**: 18 tasks (completed - OAuth authentication)
- **Phase 4 (Model Serving Config)**: 13 tasks (T068-T078h, removed fine-tuning T049-T067 and Triton T069-T072)
- **Phase 5 (US3 - Hybrid Search)**: 10 tasks
- **Phase 6 (US4 - Dataset Integration)**: 18 tasks
- **Phase 7 (US5 - Caching)**: 9 tasks
- **Phase 8 (US6 - Monitoring)**: 16 tasks (updated T113 for FastAPI metrics)
- **Phase 9 (US7 - Load Testing)**: 14 tasks
- **Phase 10 (Polish)**: 9 tasks (removed Triton optimization T150, renumbered)
- **Phase 10 (RAG Evaluation)**: 15 tasks (T156-T170, new comprehensive evaluation phase)

**Key Changes (2025-11-19)**:
- ✅ Removed 33 fine-tuning tasks (T049-T067, T078a-T078b) - out of scope
- ✅ Removed 4 Triton tasks (T005, T009, T069-T072) - replaced by FastAPI
- ✅ Added 15 RAG evaluation tasks (T156-T170) - comprehensive quality metrics
- ✅ Updated serving architecture to reflect FastAPI + remote vLLM
- ✅ Total task count reduced from 167 to 170 (net +3 for evaluation focus)

**Parallel Opportunities Identified**: 80+ tasks marked [P] can run in parallel within their phases

**Independent Test Criteria**: Each user story has clear acceptance criteria

**Suggested MVP Scope**: Phase 1 + Phase 2 + Phase 3 (User Story 1 only) = 47 tasks

**Quality Focus**:
- RAG evaluation with retrieval metrics (Recall@K, nDCG@K, MRR, Precision@K)
- Generation quality (Faithfulness, Answer Relevance, Correctness)
- Performance metrics (latency, token usage)
- Automated evaluation with DeepEval + LlamaIndex
- CI/CD integration for continuous quality monitoring

---

## Notes

- All tasks follow strict checklist format: `- [ ] [ID] [P?] [Story?] Description with file path`
- Tasks marked [P] are in different files with no dependencies - can run in parallel
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Git commit examples show natural commit messages about implemented features
- Foundational phase (Phase 2) is CRITICAL - blocks all user story work
- Tests are NOT included per MVP constitution guidelines
- Stop at any checkpoint to validate story independently before proceeding
