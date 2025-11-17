# Triton Inference Server Setup

## Architecture

- **Triton Inference Server**: Embedding, Reranking, Guardrails models (local GPU)
- **vLLM**: Generation model (remote VM - configured separately)

## Quick Start

### 1. Set Environment Variables

```bash
export HF_TOKEN="your_huggingface_token"
```

### 2. Build & Start Triton

```bash
cd serving
docker-compose build
docker-compose up -d
```

### 3. Check Status

```bash
# Check logs
docker-compose logs -f triton

# Check health
curl http://localhost:8002/v2/health/ready

# List models
curl http://localhost:8002/v2/models
```

### 4. Test Inference

**Embedding**:
```bash
curl -X POST http://localhost:8002/v2/models/qwen3_embedding/infer \
  -H "Content-Type: application/json" \
  -d '{
    "inputs": [{
      "name": "INPUT_TEXT",
      "shape": [1, 1],
      "datatype": "BYTES",
      "data": ["Triệu chứng của bệnh tiểu đường"]
    }]
  }'
```

## Ports

- **8002**: Triton HTTP
- **8003**: Triton gRPC
- **8004**: Triton Metrics

## Troubleshooting

### Model loading fails

```bash
# Check model files exist
ls -la triton/models/*/1/model.py

# Check GPU availability
nvidia-smi

# Rebuild with no cache
docker-compose build --no-cache
```

### Out of memory

- Reduce batch size in `config.pbtxt`
- Use CPU inference (remove GPU from docker-compose)

## Remote vLLM Configuration

Configure backend to call remote vLLM endpoint in `backend/config/models.yaml`:

```yaml
models:
  generation:
    endpoint: "http://REMOTE_VM_IP:8000/v1"
    model: "Qwen/Qwen3-4B-Instruct-2507"
```

## Model Details

### qwen3_embedding
- **Model**: Qwen/Qwen3-Embedding-0.6B
- **Input**: Text strings
- **Output**: 1024-dim embeddings (normalized)
- **Batch size**: 8, 16, 32

### qwen3_reranker
- **Input**: Query + Documents
- **Output**: Relevance scores
- **Batch size**: 4, 8, 16

### qwen3_guard
- **Input**: Text strings
- **Output**: Safety classification (IS_SAFE, SAFETY_SCORE)
- **Batch size**: 8, 16, 32
