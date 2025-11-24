FROM pytorch/pytorch:2.9.0-cuda12.6-cudnn9-runtime

# Install system deps
RUN apt-get update && apt-get install -y \
    curl \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies (pin versions)
RUN uv pip install --system --no-cache \
    fastapi==0.115.3 \
    uvicorn[standard]==0.25.0 \
    transformers==4.57.1 \
    sentence-transformers==5.1.2 \
    redis==5.0.7 \
    httpx==0.28.1 \
    loguru==0.7.3 \
    pydantic==2.11.9 \
    pydantic-settings==2.11.0 \
    faster-whisper==1.2.1 \
    python-multipart==0.0.18

# Copy code
# COPY serving/qwen3_models/app.py /app/app.py

EXPOSE 8002

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8002", "--workers", "1"]
