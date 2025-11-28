#!/bin/bash
set -e

echo "🚀 Starting Qwen3 Models GPU Service..."

# Check GPU availability
if command -v nvidia-smi &> /dev/null; then
    echo "✅ NVIDIA GPU detected:"
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
else
    echo "⚠️  No NVIDIA GPU detected, falling back to CPU"
fi

# Start FastAPI server
echo "🔧 Starting FastAPI server on port 8002..."
exec uvicorn app:app --host 0.0.0.0 --port 8002 --workers 1
