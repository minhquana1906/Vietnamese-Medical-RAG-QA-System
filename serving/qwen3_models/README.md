# Qwen3 Models + Whisper-turbo GPU Service

Serve 4 models (Embedding, Reranker, Guardrails, STT) trên GPU để tối ưu hiệu suất trong RAG workflow với speech-to-speech support.

## Features

- **Qwen3-Embedding-0.6B** (FP16) - Semantic embeddings
- **Qwen3-Reranker-0.6B** (FP16) - Document reranking  
- **Qwen3Guard-Gen-0.6B** (FP16) - Content safety guardrails
- **Whisper-turbo** (large-v3-turbo, FP16) - Speech-to-text with batch inference (batch_size=16)

- **GPU-accelerated inference**: Nhanh hơn 5-10x so với CPU
- **Unified service**: 1 container serve 3 models (tiết kiệm tài nguyên)
- **Auto-fallback**: Backend tự động fallback về local CPU nếu GPU service không khả dụng
- **Health monitoring**: Health check endpoint để theo dõi trạng thái

## Requirements

- **GPU**: NVIDIA GPU với CUDA support (recommended: ≥6GB VRAM)
- **Docker**: Docker Compose với NVIDIA Container Toolkit
- **VRAM**: ~4-5GB cho 3 models (FP16)

## Quick Start

### 1. Build và Start Service

```bash
cd serving/qwen3_models
docker compose up -d --build
```

### 2. Verify GPU Service

```bash
# Check logs
docker compose logs -f

# Health check
curl http://localhost:8002/health

# Expected response:
{
  "status": "healthy",
  "device": "cuda",
  "gpu_available": true,
  "models_loaded": true
}
```

### 3. Enable trong Backend

Edit `backend/.env`:
```bash
QWEN3_MODELS_URL=http://qwen3_models:8002
QWEN3_MODELS_ENABLED=true  # Set to true to use GPU service
```

Restart backend:
```bash
cd backend
docker compose restart chatbot_api chatbot_worker
```

## Architecture

```
┌─────────────────────────────────────────────────┐
│         Qwen3 Models GPU Service                │
│              (Port 8002)                        │
├─────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────┐   │
│  │   Qwen3-Embedding-0.6B (1024-dim)       │   │
│  │   - Query embedding (instruction-aware) │   │
│  │   - Document embedding                  │   │
│  └─────────────────────────────────────────┘   │
│                                                 │
│  ┌─────────────────────────────────────────┐   │
│  │   Qwen3-Reranker-0.6B (yes/no scoring)  │   │
│  │   - Document reranking                  │   │
│  │   - Relevance scoring                   │   │
│  └─────────────────────────────────────────┘   │
│                                                 │
│  ┌─────────────────────────────────────────┐   │
│  │   Qwen3Guard-Gen-0.6B (3-tier safety)   │   │
│  │   - Input validation                    │   │
│  │   - Output validation                   │   │
│  └─────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘
                      ▲
                      │ HTTP API
                      │
        ┌─────────────┴─────────────┐
        │   Backend Services        │
        │   - Embedding Service     │
        │   - Reranker Service      │
        │   - Guardrails Service    │
        └───────────────────────────┘
```

## API Endpoints

### 1. Embedding
```bash
POST http://localhost:8002/v1/models/embed
{
  "texts": ["Triệu chứng của COVID-19?"],
  "normalize": true,
  "is_query": true,
  "instruction": "Given a medical query, retrieve relevant passages"
}
```

### 2. Reranking
```bash
POST http://localhost:8002/v1/models/rerank
{
  "query": "Triệu chứng của COVID-19?",
  "documents": ["Document 1 text...", "Document 2 text..."],
  "top_n": 5,
  "instruction": "Given a medical query, determine if the passage contains the answer"
}
```

### 3. Guardrails
```bash
POST http://localhost:8002/v1/models/guard
{
  "text": "User input text...",
  "check_type": "input",
  "query": "Original query (for output check)"
}
```

## Performance Benchmarks

| Model | CPU (i7-12700K) | GPU (RTX 3090) | Speedup |
|-------|-----------------|----------------|---------|
| Embedding (batch=1) | ~200ms | ~20ms | **10x** |
| Reranking (5 docs) | ~500ms | ~50ms | **10x** |
| Guardrails | ~300ms | ~30ms | **10x** |

**Total RAG Pipeline**: ~1s (CPU) → **~100ms (GPU)** 🚀

## Configuration

### Environment Variables

```bash
# GPU device selection
CUDA_VISIBLE_DEVICES=0  # Use GPU 0 (default)
# CUDA_VISIBLE_DEVICES=1,2  # Use GPU 1 and 2

# Model paths (auto-download from HuggingFace)
EMBEDDING_MODEL=Qwen/Qwen3-Embedding-0.6B
RERANKER_MODEL=Qwen/Qwen3-Reranker-0.6B
GUARDRAILS_MODEL=Qwen/Qwen3Guard-Gen-0.6B

# Performance tuning
TORCH_NUM_THREADS=4
OMP_NUM_THREADS=4
```

### Docker Compose Override

Để sử dụng nhiều GPUs:
```yaml
# docker-compose.override.yaml
services:
  qwen3_models:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 2  # Use 2 GPUs
              capabilities: [gpu]
```

## Troubleshooting

### GPU not detected
```bash
# Check NVIDIA driver
nvidia-smi

# Check Docker GPU support
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
```

### Out of Memory (OOM)
- Giảm batch size trong code
- Sử dụng GPU với VRAM lớn hơn (≥8GB recommended)
- Disable một số models không cần thiết

### Slow first request
- First request sẽ chậm do model loading (~30s)
- Subsequent requests sẽ nhanh hơn (~20-50ms)

## Disable GPU Service

Để quay lại local CPU models:

1. Edit `backend/.env`:
```bash
QWEN3_MODELS_ENABLED=false
```

2. Restart backend:
```bash
cd backend
docker compose restart chatbot_api chatbot_worker
```

3. (Optional) Stop GPU service:
```bash
cd serving/qwen3_models
docker compose down
```

## Monitoring

```bash
# Watch GPU usage
watch -n 1 nvidia-smi

# Check service logs
docker compose logs -f qwen3_models

# Monitor API latency
curl -w "@curl-format.txt" -s http://localhost:8002/health
```

## Notes

- **VRAM Usage**: ~4-5GB cho 3 models (FP16)
- **First Request**: Chậm hơn do model loading (~30s)
- **Subsequent Requests**: Nhanh hơn 5-10x so với CPU (~20-50ms)
- **Auto-fallback**: Backend tự động fallback về CPU nếu GPU service down

## References

- [Qwen3-Embedding](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B)
- [Qwen3-Reranker](https://huggingface.co/Qwen/Qwen3-Reranker-0.6B)
- [Qwen3Guard](https://huggingface.co/Qwen/Qwen3Guard-Gen-0.6B)
