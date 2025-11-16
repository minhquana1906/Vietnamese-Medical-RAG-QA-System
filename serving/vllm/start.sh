#!/bin/bash

set -e

echo "============================================"
echo "vLLM Server Quick Start"
echo "============================================"

# Check if .env exists
if [ ! -f .env ]; then
  echo "⚠️  .env not found, creating from template..."
  cp .env.example .env
  echo "✓ Created .env file"
  echo ""
  echo "📝 Please edit .env with your configuration:"
  echo "   - MODEL_NAME: Choose your model"
  echo "   - HF_TOKEN: Add your HuggingFace token (if needed)"
  echo "   - GPU settings: Adjust for your hardware"
  echo ""
  echo "Then run: ./start.sh"
  exit 0
fi

# Check if network exists
echo "Checking Docker network..."
if ! docker network inspect medical_rag_network >/dev/null 2>&1; then
  echo "Creating medical_rag_network..."
  docker network create medical_rag_network
  echo "✓ Network created"
else
  echo "✓ Network exists"
fi

# Load environment
source .env

echo ""
echo "Configuration:"
echo "  Model: ${MODEL_NAME}"
echo "  Port: ${VLLM_PORT:-8001}"
echo "  GPU Memory: ${GPU_MEMORY_UTIL:-0.7}"
echo "  Max Length: ${MAX_MODEL_LEN:-8192}"
echo ""

# Start service
echo "Starting vLLM server..."
docker compose up -d

echo ""
echo "✓ vLLM server started!"
echo ""
echo "Monitor logs:"
echo "  docker compose logs -f"
echo ""
echo "Check health (may take 1-2 minutes):"
echo "  curl http://localhost:${VLLM_PORT:-8001}/health"
echo ""
echo "Test generation:"
echo "  curl http://localhost:${VLLM_PORT:-8001}/v1/models"
echo ""
