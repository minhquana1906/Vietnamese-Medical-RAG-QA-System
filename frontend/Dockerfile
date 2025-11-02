FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
ENV UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Copy dependency files từ root project
COPY uv.lock pyproject.toml README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev --group frontend

# Copy source code frontend
COPY frontend/ ./frontend/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --group frontend

# ======================================================================================
FROM python:3.12-slim-bookworm AS runtime

RUN groupadd --gid 1000 app && \
    useradd --uid 1000 --gid app --shell /bin/bash --create-home app

COPY --from=builder --chown=app:app /app /app

WORKDIR /app/frontend

ENV PATH="/app/.venv/bin:$PATH"

# Environment variables for Chainlit
ENV CHAINLIT_HOST=0.0.0.0
ENV CHAINLIT_PORT=8501

USER app

# Run Chainlit app
CMD ["chainlit", "run", "main.py", "--host", "0.0.0.0", "--port", "8501", "-w"]
