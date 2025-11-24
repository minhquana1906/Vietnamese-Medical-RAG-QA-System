# Model Deployment Guide

## Architecture Decision: Config File vs Database

**Decision Date**: 2025-11-15

**Approach**: HuggingFace Hub + Config File (YAML)

**Rationale**:
- **Simplicity**: Single source of truth in version-controlled config file
- **GitOps**: All deployment changes tracked in Git history
- **No DB Complexity**: No need for model management API, database table, or UI
- **HuggingFace Integration**: Leverage existing model registry and versioning
- **Operational Clarity**: Easy rollback with `git revert`

---

## Configuration File

**Location**: `backend/config/models.yaml`

```yaml
models:
  generation:
    active: "Qwen/Qwen3-4B-Instruct-2507"  # HuggingFace repo ID
    fallback: "gpt-4o-mini"                # OpenAI fallback
    description: "Main generation model for medical QA"
    
  embedding:
    active: "Qwen/Qwen3-Embedding-0.6B"
    triton_model_name: "qwen3_embedding"
    fallback: "text-embedding-3-small"
    description: "Embedding model for semantic search"
    
  reranking:
    active: "Qwen/Qwen3-Reranker-0.6B"
    triton_model_name: "qwen3_reranker"
    fallback: "rerank-english-v3.0"
    description: "Reranking model for document scoring"
    
  guardrails:
    active: "Qwen/Qwen3Guard-Gen-0.6B"
    triton_model_name: "qwen3_guard"
    threshold: 0.5
    description: "Content safety guardrails"

serving:
  # vllm_url: "http://localhost:8001"
  # triton_http_url: "http://localhost:8001"
  # triton_grpc_url: "grpc://localhost:8002"
```

---

## Deployment Workflow

### 1. Fine-Tune Model

```bash
cd ml/scripts

# Train generation model
python train_generation.py \
  --config ../configs/generation_lora_config.yaml \
  --dataset combined_medical_qa_dataset \
  --output_dir ./checkpoints/qwen3-medical-v1

# Evaluate
python evaluate_generation.py \
  --model_path ./checkpoints/qwen3-medical-v1 \
  --baseline Qwen/Qwen3-4B-Instruct-2507 \
  --test_dataset test_split
```

### 2. Upload to HuggingFace Hub

```bash
# Create model card with metrics
python upload_to_hub.py \
  --model_path ./checkpoints/qwen3-medical-v1 \
  --repo_id your-org/qwen3-medical-v1 \
  --baseline_metrics baseline_metrics.json \
  --finetuned_metrics finetuned_metrics.json

# Output: https://huggingface.co/your-org/qwen3-medical-v1
```

### 3. Update Config File

```bash
cd ../../backend

# Edit config/models.yaml
vim config/models.yaml
```

**Change**:
```yaml
models:
  generation:
    active: "your-org/qwen3-medical-v1"  # ✅ New line
    # active: "Qwen/Qwen3-4B-Instruct-2507"  # ❌ Old line (comment out)
```

### 4. Commit Changes

```bash
git add config/models.yaml
git commit -m "Deploy qwen3-medical-v1 generation model

- Fine-tuned on combined_medical_qa_dataset
- Improvement: +3.5% accuracy over baseline
- HuggingFace: your-org/qwen3-medical-v1
- W&B Run: abc123def
"

git push origin main
```

### 5. Restart Backend Service

```bash
# Development
uv run uvicorn src.main:app --reload

# Production (systemd)
sudo systemctl restart rag-backend

# Docker
docker-compose restart backend
```

### 6. (Optional) Restart vLLM

If you want vLLM to load the new model immediately:

```bash
cd ../../serving/vllm

# Update docker-compose.yml environment
vim docker-compose.yml
```

**Change**:
```yaml
environment:
  - MODEL_NAME=your-org/qwen3-medical-v1  # New model
  - HF_TOKEN=${HF_TOKEN}
```

**Restart**:
```bash
docker-compose restart vllm
```

---

## Rollback Procedure

### Quick Rollback (Git Revert)

```bash
# Find commit hash
git log --oneline | head -n 5

# Example output:
# abc1234 Deploy qwen3-medical-v1 generation model
# def5678 Update chunking strategy
# ghi9012 Fix embedding service bug

# Revert deployment
git revert abc1234

# Push
git push origin main

# Restart services
sudo systemctl restart rag-backend
docker-compose restart vllm
```

### Manual Rollback (Edit Config)

```bash
cd backend

# Edit config/models.yaml
vim config/models.yaml
```

**Revert**:
```yaml
models:
  generation:
    active: "Qwen/Qwen3-4B-Instruct-2507"  # ✅ Back to baseline
```

**Commit**:
```bash
git add config/models.yaml
git commit -m "Rollback to baseline Qwen3-4B-Instruct-2507

Reason: qwen3-medical-v1 showed performance degradation in production
"
git push origin main

sudo systemctl restart rag-backend
```

---

## Monitoring

### Check Active Models

```bash
# Read from config file
cat backend/config/models.yaml | grep "active:"

# Check backend logs
journalctl -u rag-backend -f | grep "Using active"

# Example output:
# Using active generation model from config: your-org/qwen3-medical-v1
# Initialized Qwen3EmbeddingService: HF=Qwen/Qwen3-Embedding-0.6B
```

### Verify Model Loading

```bash
# Test RAG query
curl -X POST http://localhost:8000/v1/rag \
  -H "Content-Type: application/json" \
  -d '{
    "user_identifier": "test_user",
    "thread_id": "test_thread",
    "query": "Triệu chứng của COVID-19 là gì?"
  }'

# Check vLLM model
curl http://localhost:8001/v1/models
```

---

## Best Practices

### 1. Model Naming Convention

```
<org>/<model-family>-<task>-<version>-<variant>

Examples:
- hieunguyenminh416/qwen3-medical-qa-v1.0
- hieunguyenminh416/qwen3-embedding-v2.0-medical
- hieunguyenminh416/qwen3-reranker-v1.1-clinical
```

### 2. Model Card Requirements

Every HuggingFace model must have:
- **Training Dataset**: Name and size
- **Baseline Metrics**: Accuracy, F1, BLEU, etc.
- **Fine-tuned Metrics**: Same metrics after training
- **Improvement**: Percentage improvement over baseline
- **Use Case**: Medical QA, embedding, reranking, etc.
- **Limitations**: Known issues, edge cases

### 3. Gradual Rollout

For production deployments:

1. **Canary**: Deploy to 10% of traffic
2. **Monitor**: Check error rates, latency, user feedback
3. **Scale**: Increase to 50%, then 100%
4. **Rollback**: If issues detected, revert immediately

Use feature flags or traffic splitting at load balancer level.

### 4. Version Pinning

Always use specific versions in production:

```yaml
# ✅ Good (pinned version)
active: "your-org/qwen3-medical-v1.0"

# ❌ Bad (floating version)
active: "your-org/qwen3-medical-latest"
```

### 5. Config Validation

Add pre-commit hook to validate YAML:

```bash
# .git/hooks/pre-commit
#!/bin/bash
python -c "
import yaml
with open('backend/config/models.yaml') as f:
    config = yaml.safe_load(f)
assert 'models' in config
assert all(k in config['models'] for k in ['generation', 'embedding', 'reranking', 'guardrails'])
print('✅ Config validation passed')
"
```

---

## Comparison: Config File vs Database

| Aspect | Config File (✅ Current) | Database (❌ Removed) |
|--------|--------------------------|----------------------|
| **Complexity** | Simple YAML file | DB table + API + migrations |
| **Version Control** | Built-in (Git) | Requires audit log |
| **Rollback** | `git revert` | API call + database update |
| **Visibility** | `cat config.yaml` | Query database |
| **Setup** | 1 file | Table + endpoints + schemas |
| **Operational Overhead** | Restart service | Deploy API + manage DB |
| **Multi-Environment** | Branch per environment | Database per environment |
| **Audit Trail** | Git history | Database logs |

---

## Troubleshooting

### Model Not Loading

**Symptom**: Logs show "Using active generation model from config: Qwen/Qwen3-4B-Instruct-2507" but you updated config

**Solution**:
```bash
# Config is cached at startup
# Restart backend to reload
sudo systemctl restart rag-backend

# Or use hot-reload endpoint (if implemented)
curl -X POST http://localhost:8000/admin/reload-config
```

### HuggingFace Model Not Found

**Symptom**: `Repository not found` error

**Solution**:
```bash
# Check repo exists
huggingface-cli repo info your-org/qwen3-medical-v1

# Check HF_TOKEN is set
echo $HF_TOKEN

# Login if needed
huggingface-cli login
```

### vLLM Out of Memory

**Symptom**: vLLM crashes with CUDA OOM error after loading new model

**Solution**:
```bash
# Reduce GPU memory utilization
# Edit serving/vllm/docker-compose.yml
environment:
  - GPU_MEMORY_UTIL=0.6  # Reduce from 0.7 to 0.6

# Or reduce max model length
  - MAX_MODEL_LEN=4096  # Reduce from 8192

docker-compose restart vllm
```

---

## Future Improvements

### Automated Deployment Pipeline

```yaml
# .github/workflows/deploy-model.yml
name: Deploy Model
on:
  push:
    paths:
      - 'backend/config/models.yaml'
    branches:
      - main

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Validate Config
        run: python scripts/validate_model_config.py
      - name: Restart Backend
        run: kubectl rollout restart deployment/rag-backend
      - name: Health Check
        run: |
          sleep 30
          curl -f http://rag-backend/health || exit 1
```

### Config Hot-Reload Endpoint

```python
# backend/src/main.py
@app.post("/admin/reload-config")
def reload_config():
    """Hot-reload model config without restarting service"""
    from .core.model_config import reload_config as reload_fn
    reload_fn()
    logger.info("Model config reloaded successfully")
    return {"message": "Config reloaded"}
```

### Model Performance Dashboard

- Grafana panel showing active models per type
- Metrics: inference time, throughput, error rate
- Alerts on performance degradation after deployment
