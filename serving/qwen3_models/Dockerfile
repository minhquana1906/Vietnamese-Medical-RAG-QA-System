FROM pytorch/pytorch:2.9.0-cuda12.6-cudnn9-runtime

# Install system deps
RUN apt-get update && apt-get install -y \
    curl \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies 
COPY requirements.txt /app/requirements.txt
RUN uv pip install --system --no-cache -r /app/requirements.txt

# Fix for ctranslate2/faster-whisper not finding cuDNN/cuBLAS
# We link the nvidia libraries from site-packages to /usr/lib/x86_64-linux-gnu/
RUN python3 -c "import site; import os; packages_path = site.getsitepackages()[0]; os.system(f'ln -sf {packages_path}/nvidia/cudnn/lib/libcudnn* /usr/lib/x86_64-linux-gnu/ && ln -sf {packages_path}/nvidia/cublas/lib/libcublas* /usr/lib/x86_64-linux-gnu/')" || true

EXPOSE 8002

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8002", "--workers", "1"]
