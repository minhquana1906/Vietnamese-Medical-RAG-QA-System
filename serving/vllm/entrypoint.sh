#!/bin/bash

set -e

# ============================================================================
# Configuration with sensible defaults
# ============================================================================

# Model configuration
MODEL_NAME="${MODEL_NAME:-Qwen/Qwen3-4B-Instruct-2507}"
HOST="${VLLM_HOST:-0.0.0.0}"
PORT="${VLLM_PORT:-8000}"
GPU_MEMORY_UTIL="${GPU_MEMORY_UTIL:-0.7}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-8192}"
TENSOR_PARALLEL_SIZE="${TENSOR_PARALLEL_SIZE:-1}"
DTYPE="${DTYPE:-auto}"  # auto, float16, bfloat16

# Advanced features
ENABLE_LORA="${ENABLE_LORA:-false}"
LORA_MODULES="${LORA_MODULES:-}"  # Format: name=path,name2=path2
MAX_LORAS="${MAX_LORAS:-1}"
MAX_LORA_RANK="${MAX_LORA_RANK:-16}"

# Trust remote code (required for some models like Qwen)
TRUST_REMOTE_CODE="${TRUST_REMOTE_CODE:-true}"

# ============================================================================
# Determine model path (local or HuggingFace Hub)
# ============================================================================

# If MODEL_NAME starts with /, treat as local path
# Otherwise, treat as HuggingFace repo ID
if [[ "$MODEL_NAME" == /* ]]; then
  MODEL_PATH="$MODEL_NAME"
  echo "Loading LOCAL model from: $MODEL_PATH"
  
  # Check if model directory exists
  if [ ! -d "$MODEL_PATH" ]; then
    echo "ERROR: Local model directory not found: $MODEL_PATH"
    exit 1
  fi
  
  # Check for config.json (required for vLLM)
  if [ ! -f "$MODEL_PATH/config.json" ]; then
    echo "ERROR: config.json not found in $MODEL_PATH"
    echo "vLLM requires config.json to load models"
    exit 1
  fi
else
  MODEL_PATH="$MODEL_NAME"
  echo "Loading HUGGINGFACE model: $MODEL_PATH"
  echo "Model will be downloaded if not cached"
fi

# ============================================================================
# Log configuration
# ============================================================================

echo "=========================================="
echo "vLLM Server Configuration"
echo "=========================================="
echo "Model: $MODEL_PATH"
echo "Host: $HOST:$PORT"
echo "GPU Memory Utilization: $GPU_MEMORY_UTIL"
echo "Max Model Length: $MAX_MODEL_LEN"
echo "Tensor Parallel Size: $TENSOR_PARALLEL_SIZE"
echo "Data Type: $DTYPE"
echo "Trust Remote Code: $TRUST_REMOTE_CODE"
echo "Enable LoRA: $ENABLE_LORA"
[ "$ENABLE_LORA" == "true" ] && echo "Max LoRAs: $MAX_LORAS"
[ -n "$LORA_MODULES" ] && echo "LoRA Modules: $LORA_MODULES"
echo "=========================================="

# ============================================================================
# Build vLLM command
# ============================================================================

VLLM_CMD=(
  python3 -m vllm.entrypoints.openai.api_server
  --model "$MODEL_PATH"
  --host "$HOST"
  --port "$PORT"
  --gpu-memory-utilization "$GPU_MEMORY_UTIL"
  --max-model-len "$MAX_MODEL_LEN"
  --tensor-parallel-size "$TENSOR_PARALLEL_SIZE"
  --dtype "$DTYPE"
)

# Add trust-remote-code flag if enabled
if [ "$TRUST_REMOTE_CODE" == "true" ]; then
  VLLM_CMD+=(--trust-remote-code)
fi

# Add LoRA support if enabled
if [ "$ENABLE_LORA" == "true" ]; then
  echo "Enabling LoRA support..."
  VLLM_CMD+=(
    --enable-lora
    --max-loras "$MAX_LORAS"
    --max-lora-rank "$MAX_LORA_RANK"
  )
  
  # Add LoRA modules if specified
  if [ -n "$LORA_MODULES" ]; then
    echo "Loading LoRA modules: $LORA_MODULES"
    VLLM_CMD+=(--lora-modules "$LORA_MODULES")
  fi
fi

# ============================================================================
# Execute vLLM server
# ============================================================================

echo "Starting vLLM server..."
echo "Command: ${VLLM_CMD[*]}"
echo "=========================================="

exec "${VLLM_CMD[@]}"
