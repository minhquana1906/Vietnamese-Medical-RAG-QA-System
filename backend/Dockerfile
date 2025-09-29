FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
ENV UV_PYTHON_DOWNLOADS=0

WORKDIR /app

COPY uv.lock pyproject.toml ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev --group backend

COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --group backend

# ======================================================================================
FROM python:3.12-slim-bookworm AS runtime

RUN groupadd --gid 1000 app && \
    useradd --uid 1000 --gid app --shell /bin/bash --create-home app

COPY --from=builder --chown=app:app /app /app

RUN mkdir -p /app/logs/worker /app/nltk_data && \
    chown -R app:app /app/logs/worker /app/nltk_data

WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH"
ENV NLTK_DATA="/app/nltk_data"

USER app


CMD ["/bin/bash", "-c", "python backend/scripts/init_nltk.py && uvicorn backend.src.main:app --host 0.0.0.0 --port 8000 --workers 2 --log-level info"]
