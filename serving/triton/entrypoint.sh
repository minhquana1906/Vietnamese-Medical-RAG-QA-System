#!/bin/bash
# Triton Inference Server startup script

set -e

echo "=========================================="
echo "Starting Triton Inference Server"
echo "=========================================="
echo "HuggingFace Token: ${HF_TOKEN:0:8}..."
echo "GPU Device: ${CUDA_VISIBLE_DEVICES:-0}"
echo "=========================================="

# Pre-download models to cache (optional, helps with first startup)
if [ ! -z "$HF_TOKEN" ]; then
    echo "Pre-downloading models from HuggingFace..."
    python3 -c "
from transformers import AutoModel, AutoTokenizer
import os

models = [
    'Qwen/Qwen3-Embedding-0.6B',
]

for model in models:
    print(f'Downloading {model}...')
    try:
        AutoTokenizer.from_pretrained(model, trust_remote_code=True, token=os.getenv('HF_TOKEN'))
        AutoModel.from_pretrained(model, trust_remote_code=True, token=os.getenv('HF_TOKEN'))
        print(f'✓ {model} cached')
    except Exception as e:
        print(f'⚠ Failed to cache {model}: {e}')
"
fi

# Start Triton Server
echo "Starting Triton Server..."
exec tritonserver \
    --model-repository=/models \
    --model-control-mode=explicit \
    --load-model=qwen3_embedding \
    --load-model=qwen3_reranker \
    --load-model=qwen3_guard \
    --strict-model-config=false \
    --log-verbose=1 \
    --http-port=8000 \
    --grpc-port=8001 \
    --metrics-port=8002
