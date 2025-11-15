#!/bin/bash
# vLLM Serving Script for Qwen3-4B-Instruct-2507
# This script starts vLLM server for generation model serving

set -e

# Model configuration
MODEL_NAME="${MODEL_NAME:-Qwen/Qwen3-4B-Instruct-2507}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
GPU_MEMORY_UTIL="${GPU_MEMORY_UTIL:-0.7}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-8192}"
TENSOR_PARALLEL_SIZE="${TENSOR_PARALLEL_SIZE:-1}"

# Optional: LoRA adapters (for fine-tuned models later)
LORA_MODULES="${LORA_MODULES:-}"

echo "Starting vLLM server..."
echo "Model: $MODEL_NAME"
echo "Host: $HOST:$PORT"
echo "GPU Memory Utilization: $GPU_MEMORY_UTIL"
echo "Max Model Length: $MAX_MODEL_LEN"

# Build vLLM command
VLLM_CMD="vllm serve $MODEL_NAME \
  --host $HOST \
  --port $PORT \
  --gpu-memory-utilization $GPU_MEMORY_UTIL \
  --max-model-len $MAX_MODEL_LEN \
  --tensor-parallel-size $TENSOR_PARALLEL_SIZE \
  --trust-remote-code"

# Add LoRA support if modules specified
if [ -n "$LORA_MODULES" ]; then
  echo "LoRA modules: $LORA_MODULES"
  VLLM_CMD="$VLLM_CMD --enable-lora --lora-modules $LORA_MODULES"
fi

# Execute
exec $VLLM_CMD
