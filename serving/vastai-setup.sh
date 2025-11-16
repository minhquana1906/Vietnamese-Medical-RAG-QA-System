#!/bin/bash
# Vast.ai GPU Instance Setup Script
# Run this script on your rented Vast.ai instance

set -e

echo "🚀 Setting up Vast.ai GPU instance for model serving..."

# 1. Install Docker if not exists
if ! command -v docker &> /dev/null; then
    echo "📦 Installing Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
fi

# 2. Install Docker Compose
# if ! command -v docker-compose &> /dev/null; then
#     echo "📦 Installing Docker Compose..."
#     sudo curl -L "https://github.com/docker/compose/releases/download/v2.23.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
#     sudo chmod +x /usr/local/bin/docker-compose
# fi

# 3. Clone repository
if [ ! -d "Vietnamese-Medical-RAG-QA-System" ]; then
    echo "📥 Cloning repository..."
    git clone https://github.com/minhquana1906/Vietnamese-Medical-RAG-QA-System.git
fi

cd Vietnamese-Medical-RAG-QA-System

git checkout 001-improve-rag-system

# 4. Create network
docker network create medical_rag_network || true

# 5. Setup environment variables
cat > serving/vllm/.env <<EOF
HF_TOKEN=${HF_TOKEN}
MODEL_NAME=Qwen/Qwen3-4B-Instruct-2507
VLLM_PORT=8001
GPU_MEMORY_UTIL=0.6
MAX_MODEL_LEN=8192
TENSOR_PARALLEL_SIZE=1
EOF

cat > serving/triton/.env <<EOF
HF_TOKEN=${HF_TOKEN}
CUDA_VISIBLE_DEVICES=0
EOF

# 6. Start model serving services
echo "🔥 Starting vLLM (Generation model)..."
cd serving/vllm
docker-compose up -d

echo "🔥 Starting Triton (Embedding, Reranking, Guardrails)..."
cd ../triton
docker-compose up -d

# 7. Wait for services to be healthy
echo "⏳ Waiting for services to be ready..."
sleep 60

# 8. Health check
echo "🏥 Health check..."
curl -f http://localhost:8001/health && echo "✅ vLLM is healthy"
curl -f http://localhost:8002/v2/health/ready && echo "✅ Triton is healthy"

echo "✅ Setup completed! Services are running on:"
echo "  - vLLM (Generation): http://$(curl -s ifconfig.me):8001"
echo "  - Triton (Others): http://$(curl -s ifconfig.me):8002"
