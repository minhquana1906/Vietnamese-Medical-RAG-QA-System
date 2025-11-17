FROM nvcr.io/nvidia/tritonserver:24.01-py3

# Install Python dependencies for model inference
RUN pip install --no-cache-dir \
    torch==2.2.0 \
    transformers==4.57.0 \
    numpy==1.24.3 \
    sentencepiece \
    protobuf

# Create cache directory
RUN mkdir -p /root/.cache/huggingface

# Set environment variables
ENV HF_HOME=/root/.cache/huggingface

WORKDIR /models

