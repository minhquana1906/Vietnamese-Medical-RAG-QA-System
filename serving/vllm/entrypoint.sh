#!/bin/bash
set -e

export HF_TOKEN=$HF_TOKEN
export VLLM_API_KEY=$VLLM_API_KEY

PORT=8000
HOST=0.0.0.0

# Check uv installation
UV_CMD=$(which uv 2>/dev/null)
if [ -z "$UV_CMD" ]; then
  echo "uv executable not found!"
  exit 1
fi

echo "Using uv executable: $UV_CMD"

# Start vLLM
echo "Starting vLLM..."
exec uv run -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen3-4B-Instruct-2507 \
  --host ${HOST} \
  --port ${PORT} \
  --gpu-memory-utilization 0.9 \
  --swap-space 10 \
  --enable-prefix-caching \
  --max-model-len 8192 \
  --trust-remote-code \
  --device cuda


# Store the PID of the background process
VLLM_PID=$!

# Function to check if the API is ready
wait_for_api() {
  echo "Waiting for vLLM API to be ready..."
  local retries=0
  # local max_retries=30
  while ! curl -s -H "Authorization: Bearer $VLLM_API_KEY" http://localhost:8000/v1/models > /dev/null; do
    retries=$((retries + 1))
    echo "API not ready yet, waiting... (Attempt: $retries - $((retries * 10)) seconds passed)"
    sleep 10
  done
  echo "vLLM API is ready!"
}


# Debugging: Check GPU availability
check_gpu() {
  echo "Checking GPU availability..."
  if ! nvidia-smi > /dev/null 2>&1; then
    echo "GPU is not available. Ensure NVIDIA drivers and container runtime are properly configured."
    exit 1
  fi
  echo "GPU is available."
}

# Run debugging checks
check_gpu

# Wait for the API to be ready
wait_for_api

# Wait for the vllm process
wait $VLLM_PID
