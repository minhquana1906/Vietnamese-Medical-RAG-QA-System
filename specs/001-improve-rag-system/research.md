# Research & Technical Decisions

**Feature**: RAG System Comprehensive Improvements
**Phase**: 0 - Research & Resolution
**Date**: 2025-10-31

## Overview

This document captures research findings and technical decisions for all major components of the RAG system upgrade. Each section addresses key unknowns from the Technical Context and provides rationale for chosen approaches.

---

## 1. Chainlit Integration for RAG-Native UI

### Decision
Adopt **Chainlit** as the frontend framework, replacing Streamlit, with SQLAlchemy-based data layer for user and session management.

### Rationale
- **RAG-Native Features**: Built-in support for streaming responses, conversation history, and session lifecycle management
- **Authentication**: Native support for email/password + OAuth providers (Google, GitHub, etc.)
- **Persistent Sessions**: Automatic chat session management with database backing
- **Developer Experience**: Decorators for message handlers, callbacks for user actions
- **SQLAlchemy Integration**: Official recommendation to use SQLAlchemy for `User`, `Thread`, and `Step` tables (compatible with existing Alembic migrations)

### Implementation Approach
```python
# Chainlit app structure
@cl.on_chat_start
async def start():
    # Initialize chat session

@cl.on_message
async def main(message: cl.Message):
    # Handle user message with RAG pipeline

@cl.password_auth_callback
async def auth_callback(username: str, password: str):
    # Custom authentication logic
```

**Database Schema**: Follow [Chainlit SQLAlchemy guide](https://docs.chainlit.io/data-layers/sqlalchemy) with tables:
- `users` (id, email, password_hash, oauth_provider, created_at)
- `threads` (id, user_id, name, created_at, metadata)
- `steps` (id, thread_id, type, content, created_at)

### Alternatives Considered
- **Streamlit + Custom Auth**: Rejected due to lack of native session management and OAuth support
- **Custom React Frontend**: Rejected due to MVP timeline and complexity overhead
- **Gradio**: Rejected due to inferior session management compared to Chainlit

### References
- [Chainlit Documentation](https://docs.chainlit.io)
- [Chainlit SQLAlchemy Data Layer](https://docs.chainlit.io/data-layers/sqlalchemy)
- [Chainlit Authentication](https://docs.chainlit.io/authentication/overview)

---

## 2. Qwen3 Model Fine-tuning with LoRA/QLoRA

### Decision
Use **LoRA (Low-Rank Adaptation)** for fine-tuning with **bitsandbytes quantization** (4-bit or FP16 depending on VRAM availability) for both generation and embedding models.

### Rationale
- **VRAM Efficiency**: LoRA reduces trainable parameters by 90%+ (e.g., 4B model → ~400M trainable params), enabling fine-tuning on single GPU
- **Training Speed**: Faster convergence compared to full fine-tuning
- **Quantization**: bitsandbytes 4-bit quantization further reduces memory footprint (crucial for vast.ai GPU instances)
- **Qwen3 Compatibility**: Qwen team provides official LoRA fine-tuning examples

### Implementation Approach

**Generation Model (Qwen3-4B-Instruct-2507)**:
```python
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, BitsAndBytesConfig

# Quantization config
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.float16
)

# LoRA config
lora_config = LoraConfig(
    r=16,  # rank
    lora_alpha=32,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM"
)

model = AutoModelForCausalLM.from_pretrained(
    "Qwen/Qwen3-4B-Instruct-2507",
    quantization_config=bnb_config
)
model = get_peft_model(model, lora_config)
```

**Embedding Model (Qwen3-Embedding-0.6B)**:
- Similar LoRA approach with `task_type="FEATURE_EXTRACTION"`
- Contrastive learning objective on paired Vietnamese medical queries/documents
- Fine-tuning on [vietnamese-medical-dataset](https://huggingface.co/datasets/mtue29/vietnamese-medical-dataset)

**Training Datasets**:
- Generation: [combined_medical_qa_dataset](https://huggingface.co/datasets/quannguyen204/combined_medical_qa_dataset)
- Embedding: [vietnamese-medical-dataset](https://huggingface.co/datasets/mtue29/vietnamese-medical-dataset)

### Baseline Evaluation Strategy
1. **Generation Model**: BLEU, ROUGE-L, BERTScore on held-out test set (20% split)
2. **Embedding Model**: Retrieval metrics (Precision@K, Recall@K, MRR) on document retrieval task
3. **Threshold**: 2-5% improvement required for deployment (per user specification)

### Alternatives Considered
- **Full Fine-tuning**: Rejected due to VRAM constraints (requires 4x more memory)
- **Adapter Tuning**: Rejected in favor of LoRA (better performance-efficiency trade-off)
- **Prompt Engineering Only**: Rejected as insufficient for domain-specific Vietnamese medical terminology

### References
- [Qwen3-4B-Instruct-2507 Model Card](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507)
- [Qwen3-Embedding-0.6B Model Card](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B)
- [LoRA Paper](https://arxiv.org/abs/2106.09685)
- [bitsandbytes Documentation](https://github.com/TimDettmers/bitsandbytes)

---

## 3. Model Serving Architecture: vLLM + Triton

### Decision
- **vLLM** for generation model (Qwen3-4B-Instruct-2507)
- **NVIDIA Triton Inference Server** for embedding, reranking, and guardrails models

### Rationale

**vLLM for Generation**:
- **PagedAttention**: Efficient KV cache management for higher throughput
- **Continuous Batching**: Handles multiple requests concurrently with dynamic batching
- **Tensor Parallelism**: Supports multi-GPU if needed (future scaling)
- **OpenAI-Compatible API**: Easy integration with existing OpenAI fallback code

**Triton for Smaller Models**:
- **Efficient Batching**: Dynamic batching for embedding/reranking requests
- **Multi-Model Serving**: Host 3 models (embedding, reranker, guardrails) on single instance
- **Python Backend**: Easy integration with HuggingFace transformers
- **Lower Latency**: Optimized for smaller models (<1B parameters)

### Implementation Approach

**vLLM Serving**:
```bash
vllm serve Qwen/Qwen3-4B-Instruct-2507 \
    --host 0.0.0.0 \
    --port 8001 \
    --gpu-memory-utilization 0.7 \
    --max-model-len 8192 \
    --enable-lora \
    --lora-modules qwen3-medical-gen=/path/to/lora_adapters
```

**Triton Model Repository Structure**:
```
models/
├── qwen3_embedding/
│   ├── config.pbtxt        # Model configuration
│   └── 1/
│       └── model.py        # Python backend with transformers
├── qwen3_reranker/
│   └── ...
└── qwen3_guard/
    └── ...
```

### Alternatives Considered
- **Text Generation Inference (TGI)**: Rejected in favor of vLLM (better performance, more mature)
- **Single Triton for All Models**: Rejected as vLLM is specialized for generation tasks
- **FastAPI + Transformers**: Rejected due to lack of batching and optimization

### References
- [vLLM Documentation](https://docs.vllm.ai)
- [Triton Inference Server User Guide](https://docs.nvidia.com/deeplearning/triton-inference-server/user-guide/docs/index.html)
- [Triton Python Backend](https://github.com/triton-inference-server/python_backend)

---

## 4. Hybrid Search with Reciprocal Rank Fusion

### Decision
Implement **hybrid search** combining Qdrant (vector) + Elasticsearch (keyword) with **Reciprocal Rank Fusion (RRF)** for result merging.

### Rationale
- **Complementary Strengths**: Vector search captures semantic similarity, keyword search handles exact matches (drug names, medical codes)
- **RRF Simplicity**: Parameter-free fusion algorithm that balances both rankings
- **Proven Effectiveness**: RRF consistently outperforms weighted averaging in IR literature
- **Single Fixed Strategy**: Per user specification, use consistent chunking across all document types

### Implementation Approach

```python
def hybrid_search(query: str, top_k: int = 20) -> List[Document]:
    # 1. Generate embedding for semantic search
    query_embedding = embedding_service.embed(query)

    # 2. Vector search (Qdrant)
    vector_results = qdrant_client.search(
        collection_name="medical_docs",
        query_vector=query_embedding,
        limit=top_k
    )

    # 3. Keyword search (Elasticsearch)
    keyword_results = es_client.search(
        index="medical_docs",
        body={
            "query": {"multi_match": {"query": query, "fields": ["content", "title"]}},
            "size": top_k
        }
    )

    # 4. Apply RRF
    rrf_k = 60  # Standard RRF constant
    fused_scores = {}

    for rank, doc in enumerate(vector_results, 1):
        fused_scores[doc.id] = 1 / (rrf_k + rank)

    for rank, doc in enumerate(keyword_results, 1):
        fused_scores[doc.id] = fused_scores.get(doc.id, 0) + 1 / (rrf_k + rank)

    # 5. Sort by fused score and return top-k
    return sorted(documents, key=lambda d: fused_scores[d.id], reverse=True)[:top_k]
```

### Chunking Strategy
- **Single Fixed Strategy**: Semantic chunking with sentence boundary awareness
- **Chunk Size**: 512 tokens (configurable)
- **Overlap**: 50 tokens to preserve context
- **Method**: Use sentence tokenizer (NLTK) to avoid mid-sentence breaks

### Alternatives Considered
- **Adaptive Chunking by Document Type**: Rejected per user specification (Option B: single fixed strategy)
- **Weighted Linear Combination**: Rejected in favor of RRF (no hyperparameters to tune)
- **Vector-Only Search**: Rejected as insufficient for exact medical term matching

### References
- [RRF Original Paper](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf)
- [Qdrant Hybrid Search Guide](https://qdrant.tech/documentation/tutorials/hybrid-search/)
- [Elasticsearch BM25](https://www.elastic.co/docs)

---

## 5. Caching Layer Design

### Decision
Implement **Redis-based caching** for query embeddings and search results with LRU eviction policy.

### Rationale
- **Existing Infrastructure**: Redis already used for Celery, no new dependency
- **Fast Access**: In-memory cache with <1ms latency
- **TTL Support**: Automatic expiration for stale data
- **LRU Eviction**: Efficient memory management when cache is full

### Implementation Approach

```python
import redis
import hashlib
import json

class RAGCache:
    def __init__(self, redis_client):
        self.client = redis_client
        self.embedding_ttl = 3600  # 1 hour
        self.search_ttl = 600      # 10 minutes

    def get_query_embedding(self, query: str):
        key = f"emb:{hashlib.md5(query.encode()).hexdigest()}"
        cached = self.client.get(key)
        if cached:
            return json.loads(cached)
        return None

    def cache_query_embedding(self, query: str, embedding: List[float]):
        key = f"emb:{hashlib.md5(query.encode()).hexdigest()}"
        self.client.setex(key, self.embedding_ttl, json.dumps(embedding))

    def get_search_results(self, query: str, search_type: str):
        key = f"search:{search_type}:{hashlib.md5(query.encode()).hexdigest()}"
        cached = self.client.get(key)
        if cached:
            return json.loads(cached)
        return None

    def cache_search_results(self, query: str, search_type: str, results):
        key = f"search:{search_type}:{hashlib.md5(query.encode()).hexdigest()}"
        self.client.setex(key, self.search_ttl, json.dumps(results))
```

### Cache Invalidation Strategy
- **TTL-Based**: Embeddings expire after 1 hour, search results after 10 minutes
- **Document Updates**: Clear all search caches when documents are reindexed
- **Manual Flush**: Admin endpoint to clear cache if needed

### Alternatives Considered
- **In-Memory Python Dict**: Rejected due to lack of persistence and distributed access
- **Memcached**: Rejected as Redis already in stack with richer feature set
- **No Caching**: Rejected due to performance requirements (SC-013: ≥30% cache hit rate)

### References
- [Redis Caching Patterns](https://redis.io/docs/manual/patterns/caching/)
- [Redis TTL Documentation](https://redis.io/commands/ttl/)

---

## 6. Observability Stack: Prometheus, Loki, Tempo, Grafana

### Decision
Deploy full observability stack with:
- **Prometheus**: Metrics scraping and storage
- **Promtail + Loki**: Log aggregation
- **Tempo**: Distributed tracing
- **Grafana**: Unified visualization with pre-built dashboards

### Rationale
- **User Specification**: Explicitly requested this stack
- **Comprehensive Coverage**: Metrics, logs, and traces cover all observability pillars
- **Pre-built Dashboards**: Grafana community has existing RAG and ML serving dashboards
- **Correlation**: Grafana enables correlation between metrics, logs, and traces in single view

### Implementation Approach

**Prometheus Metrics** (exposed by FastAPI app):
```python
from prometheus_client import Counter, Histogram, Gauge

# Metrics
rag_requests_total = Counter('rag_requests_total', 'Total RAG requests')
rag_request_duration = Histogram('rag_request_duration_seconds', 'RAG request duration')
cache_hits = Counter('cache_hits_total', 'Cache hits', ['cache_type'])
model_inference_duration = Histogram('model_inference_duration_seconds', 'Model inference time', ['model'])
active_users = Gauge('active_users', 'Number of active users')
```

**Structured Logging** (Loguru with JSON formatter):
```python
from loguru import logger

logger.add(
    "logs/app.log",
    format="{time} | {level} | {message}",
    serialize=True,  # JSON output
    rotation="100 MB"
)

# Usage
logger.info(
    "RAG pipeline executed",
    user_id=user_id,
    query=query,
    retrieval_count=len(docs),
    rerank_time=rerank_time,
    generation_time=gen_time
)
```

**Distributed Tracing** (OpenTelemetry):
```python
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

tracer = trace.get_tracer(__name__)

@tracer.start_as_current_span("rag_pipeline")
async def rag_pipeline(query: str):
    with tracer.start_as_current_span("embedding"):
        embedding = await embed(query)

    with tracer.start_as_current_span("retrieval"):
        docs = await retrieve(embedding)

    with tracer.start_as_current_span("reranking"):
        ranked_docs = await rerank(query, docs)

    with tracer.start_as_current_span("generation"):
        response = await generate(query, ranked_docs)

    return response
```

**Grafana Dashboards** (use existing templates):
- [FastAPI Observability Dashboard](https://grafana.com/grafana/dashboards/16110)
- [Prometheus Node Exporter](https://grafana.com/grafana/dashboards/1860)
- [Loki Dashboard](https://grafana.com/grafana/dashboards/13639)
- Custom RAG pipeline dashboard (will be created based on metrics above)

### Alternatives Considered
- **ELK Stack**: Rejected per user specification (already using Elasticsearch for search)
- **Simple File Logging**: Rejected as insufficient for distributed system observability
- **DataDog/New Relic**: Rejected due to cost and MVP timeline

### References
- [Grafana Documentation](https://grafana.com/docs/)
- [Prometheus Best Practices](https://prometheus.io/docs/practices/)
- [Loki Documentation](https://grafana.com/docs/loki/latest/)
- [Tempo Documentation](https://grafana.com/docs/tempo/latest/)
- [OpenTelemetry Python](https://opentelemetry.io/docs/instrumentation/python/)

---

## 7. HuggingFace Hub & W&B Integration

### Decision
- **HuggingFace Hub**: Model and dataset registry
- **Weights & Biases (W&B)**: Experiment tracking during fine-tuning

### Rationale

**HuggingFace Hub**:
- **Centralized Storage**: Store fine-tuned models, datasets, and evaluation results
- **Version Control**: Track model versions with git-like interface
- **Model Cards**: Detailed documentation for each artifact (required per user specification)
- **Easy Download**: `huggingface_hub` library for programmatic access

**W&B**:
- **Experiment Tracking**: Log training metrics, hyperparameters, and artifacts
- **Comparison**: Compare baseline vs fine-tuned model performance
- **Visualization**: Real-time training curves and evaluation metrics

### Implementation Approach

**Upload to HuggingFace Hub**:
```python
from huggingface_hub import HfApi, create_repo

api = HfApi()

# Create repository
create_repo(
    repo_id="quannguyen204/qwen3-4b-medical-finetuned",
    private=False,
    repo_type="model"
)

# Upload model with detailed README
api.upload_folder(
    folder_path="./fine_tuned_model",
    repo_id="quannguyen204/qwen3-4b-medical-finetuned",
    commit_message="Fine-tuned on Vietnamese medical QA dataset"
)

# Model card template
README_TEMPLATE = """
---
language: vi
license: apache-2.0
tags:
  - qwen3
  - medical
  - vietnamese
  - rag
---

# Qwen3-4B Medical Fine-tuned

Fine-tuned version of Qwen3-4B-Instruct-2507 on Vietnamese medical QA dataset.

## Training Details

- **Base Model**: Qwen/Qwen3-4B-Instruct-2507
- **Dataset**: quannguyen204/combined_medical_qa_dataset
- **Method**: LoRA (r=16, alpha=32) with 4-bit quantization
- **Training Steps**: 10,000
- **Evaluation**: BLEU: 0.XX, ROUGE-L: 0.XX (X% improvement over baseline)

## Usage

[Include inference code]
"""
```

**W&B Tracking**:
```python
import wandb

# Initialize run
wandb.init(
    project="vietnamese-medical-rag",
    name="qwen3-generation-finetune",
    config={
        "learning_rate": 2e-4,
        "lora_r": 16,
        "lora_alpha": 32,
        "batch_size": 4,
        "epochs": 3
    }
)

# Log during training
wandb.log({
    "train/loss": loss,
    "train/perplexity": perplexity,
    "eval/bleu": bleu_score
})

# Log final model
wandb.log_artifact(model_path, name="qwen3-medical-gen", type="model")
```

### Alternatives Considered
- **Local Storage Only**: Rejected due to lack of version control and collaboration features
- **MLflow**: Rejected as W&B has better UI and HuggingFace integration
- **Git LFS**: Rejected in favor of HuggingFace Hub (built for ML artifacts)

### References
- [HuggingFace Hub Documentation](https://huggingface.co/docs/huggingface_hub/en/guides/model-cards)
- [W&B Documentation](https://docs.wandb.ai/)
- [HuggingFace Hub Python Client](https://huggingface.co/docs/huggingface_hub/en/index)

---

## 8. Load Testing with Locust

### Decision
Use **Locust** for load and stress testing with custom scenarios for RAG queries.

### Rationale
- **Python-Native**: Easy integration with FastAPI backend
- **Distributed Testing**: Scale to multiple workers if needed
- **Real-Time UI**: Web interface for monitoring test progress
- **Flexible Scenarios**: Define custom user behaviors for RAG queries

### Implementation Approach

```python
# locustfile.py
from locust import HttpUser, task, between
import random

class RAGUser(HttpUser):
    wait_time = between(1, 3)  # Wait 1-3 seconds between requests

    medical_queries = [
        "Triệu chứng của bệnh tiểu đường là gì?",
        "Cách điều trị cao huyết áp",
        "Thuốc paracetamol dùng như thế nào?",
        # ... more queries
    ]

    @task(3)  # Weight: 3x more common
    def simple_query(self):
        """Simple medical question"""
        query = random.choice(self.medical_queries)
        self.client.post("/chat/complete", json={
            "bot_id": "medical_bot",
            "user_id": f"user_{self.user_id}",
            "user_message": query,
            "is_sync_request": True
        })

    @task(1)
    def complex_query(self):
        """Complex multi-part question"""
        query = "Tôi bị đau đầu và sốt, nên uống thuốc gì và liều lượng ra sao?"
        self.client.post("/chat/complete", json={
            "bot_id": "medical_bot",
            "user_id": f"user_{self.user_id}",
            "user_message": query,
            "is_sync_request": True
        })

# Run with: locust -f locustfile.py --host=http://localhost:8000 --users=100 --spawn-rate=10
```

**Test Scenarios**:
1. **Load Test**: 100 concurrent users, 10 users/second spawn rate, 10 minute duration
2. **Stress Test**: Gradually increase from 10 to 500 users to find breaking point
3. **Spike Test**: Sudden jump from 10 to 200 users to test elasticity

### Success Criteria Validation
- SC-012: p95 response time <5 seconds
- SC-014: 100 concurrent users with <1% error rate
- SC-015: 1 hour sustained load with stable performance

### Alternatives Considered
- **Apache JMeter**: Rejected due to Java dependency and less Python-friendly
- **k6**: Rejected as Locust better integrates with Python ecosystem
- **Manual curl scripts**: Rejected as insufficient for realistic load patterns

### References
- [Locust Documentation](https://docs.locust.io/)
- [Locust Best Practices](https://docs.locust.io/en/stable/writing-a-locustfile.html)

---

## Summary of Key Decisions

| Component | Technology Choice | Rationale |
|-----------|-------------------|-----------|
| Frontend UI | Chainlit | RAG-native, built-in auth & sessions |
| Fine-tuning | LoRA + bitsandbytes | VRAM efficiency, fast training |
| Generation Serving | vLLM | PagedAttention, continuous batching |
| Other Models Serving | NVIDIA Triton | Efficient batching for smaller models |
| Hybrid Search | Qdrant + Elasticsearch + RRF | Semantic + keyword, parameter-free fusion |
| Chunking | Fixed semantic strategy | Single approach per user spec (Option B) |
| Caching | Redis (existing infra) | Fast, supports TTL and LRU |
| Metrics | Prometheus | Industry standard, good ecosystem |
| Logs | Promtail + Loki | Grafana-native, efficient storage |
| Traces | Tempo | Grafana-native, distributed tracing |
| Visualization | Grafana 12.2 | Pre-built dashboards, unified view |
| Model Registry | HuggingFace Hub | Version control, model cards, easy sharing |
| Experiment Tracking | Weights & Biases | Real-time monitoring, comparison UI |
| Load Testing | Locust | Python-native, flexible scenarios |

---

## Next Steps

Proceed to **Phase 1** to generate:
1. `data-model.md`: Entity definitions and relationships
2. `contracts/`: API endpoint specifications
3. `quickstart.md`: Setup and validation instructions
