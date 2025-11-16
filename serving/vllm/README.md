# vLLM Generation Model Serving

Production-ready vLLM deployment for Vietnamese Medical RAG system.

## Quick Start

```bash
# 1. Copy environment template
cp .env.example .env

# 2. Edit .env with your configuration
nano .env

# 3. Start vLLM server
docker compose up -d

# 4. Check logs
docker compose logs -f

# 5. Test health
curl http://localhost:8001/health
```

## Configuration Options

### Using HuggingFace Hub (Recommended)

**Pros**: No manual download, automatic caching, easy updates
**Cons**: Requires internet on first run

```bash
# .env
MODEL_NAME=Qwen/Qwen2.5-3B-Instruct
```

### Using Local Models

**Pros**: No internet required, faster startup after download
**Cons**: Manual download, more storage management

```bash
# 1. Download model manually
huggingface-cli download Qwen/Qwen2.5-3B-Instruct --local-dir ./models/qwen2.5-3b

# 2. Configure .env
MODEL_NAME=/models/qwen2.5-3b
MODEL_PATH=./models/qwen2.5-3b
```

## Performance Tuning

### Single GPU (Default)

```bash
GPU_COUNT=1
TENSOR_PARALLEL_SIZE=1
GPU_MEMORY_UTIL=0.7
```

### Multi-GPU

```bash
GPU_COUNT=2
TENSOR_PARALLEL_SIZE=2
CUDA_VISIBLE_DEVICES=0,1
GPU_MEMORY_UTIL=0.8
```

### Memory Optimization

- **Low VRAM** (< 8GB): Use smaller model, reduce `MAX_MODEL_LEN`
- **High VRAM** (>= 24GB): Increase `GPU_MEMORY_UTIL` to 0.9

```bash
# For RTX 3060 12GB
MAX_MODEL_LEN=4096
GPU_MEMORY_UTIL=0.65

# For A100 40GB
MAX_MODEL_LEN=16384
GPU_MEMORY_UTIL=0.9
```

## LoRA Fine-tuned Models

### Enable LoRA Support

```bash
ENABLE_LORA=true
MAX_LORAS=2
```

### Load LoRA Adapters

```bash
# Place LoRA adapters in ./models/lora/
LORA_MODULES=medical-v1=/models/lora/medical-v1,medical-v2=/models/lora/medical-v2
```

### Request with LoRA

```bash
curl http://localhost:8001/v1/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "medical-v1",
    "prompt": "What is diabetes?",
    "max_tokens": 100
  }'
```

## API Usage

### Health Check

```bash
curl http://localhost:8001/health
```

### List Models

```bash
curl http://localhost:8001/v1/models
```

### Completion (Text Generation)

```bash
curl http://localhost:8001/v1/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen2.5-3B-Instruct",
    "prompt": "What is diabetes?",
    "max_tokens": 100,
    "temperature": 0.7
  }'
```

### Chat Completion

```bash
curl http://localhost:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen2.5-3B-Instruct",
    "messages": [
      {"role": "system", "content": "You are a medical assistant."},
      {"role": "user", "content": "What is diabetes?"}
    ],
    "max_tokens": 100
  }'
```

## Troubleshooting

### Error: `Unsupported config format: ConfigFormat.AUTO`

**Cause**: vLLM v0.8.0 bug when loading local models without proper config.json

**Solution**:
1. Use HuggingFace Hub model ID instead: `MODEL_NAME=Qwen/Qwen2.5-3B-Instruct`
2. Or ensure local model has valid `config.json`

### Error: `CUDA out of memory`

**Solutions**:
- Reduce `GPU_MEMORY_UTIL` (try 0.6 or 0.5)
- Reduce `MAX_MODEL_LEN` (try 4096 or 2048)
- Use smaller model (Qwen2.5-1.5B-Instruct)

### Container keeps restarting

**Check logs**:
```bash
docker compose logs vllm
```

**Common issues**:
- Invalid `MODEL_NAME` or `MODEL_PATH`
- Insufficient GPU memory
- Missing `config.json` for local models

### Slow startup

**Normal behavior**: First run downloads model (can take 5-20 minutes depending on model size and network)

**Speed up**:
- Use local models (download once)
- Increase network bandwidth
- Use SSD for model cache

## Monitoring

### Container Stats

```bash
docker stats vllm_server
```

### Resource Usage

```bash
nvidia-smi  # GPU usage
docker exec vllm_server nvidia-smi
```

### Logs

```bash
# Follow logs
docker compose logs -f

# Last 100 lines
docker compose logs --tail=100

# Since 10 minutes ago
docker compose logs --since=10m
```

## Deployment Workflow

### 1. Development (Local Testing)

```bash
MODEL_NAME=Qwen/Qwen2.5-3B-Instruct
docker compose up
```

### 2. Fine-tuned Model

```bash
# After fine-tuning, upload to HuggingFace Hub
huggingface-cli upload your-org/qwen2.5-medical-v1 ./output/final_model

# Deploy
MODEL_NAME=your-org/qwen2.5-medical-v1
docker compose up -d
```

### 3. LoRA Adapter

```bash
# Copy LoRA adapter to models directory
cp -r ./output/lora_adapter ./models/lora/medical-v1

# Enable LoRA
ENABLE_LORA=true
LORA_MODULES=medical-v1=/models/lora/medical-v1
docker compose up -d
```

## Production Checklist

- [ ] Set `restart: unless-stopped` in docker-compose.yml ✅
- [ ] Configure health check ✅
- [ ] Set resource limits (memory, GPU) ✅
- [ ] Enable log rotation ✅
- [ ] Use external network for service communication ✅
- [ ] Set up monitoring (Prometheus + Grafana)
- [ ] Configure backup for model cache
- [ ] Use `.env` file for sensitive data (HF_TOKEN) ✅

## References

- [vLLM Documentation](https://docs.vllm.ai)
- [OpenAI-Compatible API](https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html)
- [LoRA Support](https://docs.vllm.ai/en/latest/models/lora.html)
