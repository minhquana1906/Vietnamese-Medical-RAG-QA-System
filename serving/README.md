# Model Serving Infrastructure

See detailed guide: [TRITON_LOCAL_SETUP.md](../docs/TRITON_LOCAL_SETUP.md)

## Quick Start

```bash
# Set HuggingFace token
export HF_TOKEN="your_token"

# Start Triton
docker-compose up -d triton

# Verify health
curl http://localhost:8002/v2/health/ready
curl http://localhost:8002/v2/models | jq
```

## Architecture

- **Generation Model**: Remote vLLM server (http://112.84.166.37:20362)
- **Triton Models** (Local GPU):
  - qwen3_embedding: Semantic search embeddings
  - qwen3_reranker: Document reranking
  - qwen3_guard: Content safety guardrails

## Ports

- 8002: Triton HTTP
- 8003: Triton gRPC  
- 8004: Triton Metrics

## Configuration

Backend config: `backend/config/models.yaml`

```yaml
serving:
  vllm_url: "http://112.84.166.37:20362"
  triton_http_url: "http://localhost:8002"
  triton_grpc_url: "grpc://localhost:8003"
```
