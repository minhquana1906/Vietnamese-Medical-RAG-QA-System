
FROM python:3.12-slim-bookworm AS builder

WORKDIR /app

COPY frontend/requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt

COPY frontend/. .

# ======================================================================================
FROM python:3.12-slim-bookworm AS runtime

RUN groupadd --gid 1000 app && \
    useradd --uid 1000 --gid app --shell /bin/bash --create-home app

COPY --from=builder --chown=app:app /app /app

WORKDIR /app

RUN pip install --no-cache-dir -r requirements.txt


USER app

EXPOSE 8501

CMD ["chainlit", "run", "main.py", "--port", "8501", "--host", "0.0.0.0"]
