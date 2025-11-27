import os
import sys
import pytest
from unittest.mock import MagicMock, AsyncMock

# Ensure backend/src is on path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app():
    """Create a FastAPI app for tests.

    If env `USE_REAL_APP` is set (truthy), import the real app from `src.main` and use it.
    Otherwise return a lightweight mocked app for fast unit tests.
    """

    # If the user wants to test against the real app, import it and return it
    # unmodified. This will cause tests to surface real dependency errors when
    # `.env` or external services are not available.
    use_real = os.environ.get("USE_REAL_APP", "1").lower() in ("1", "true", "yes")
    if use_real:
        try:
            # Import the real FastAPI app from the project
            from src.main import app as real_app  # type: ignore
        except Exception as exc:  # pragma: no cover - environment specific
            raise RuntimeError(
                "Failed to import real app from src.main. Ensure dependencies and env are set: ``USE_REAL_APP=1`` "
            ) from exc
        return real_app

    app = FastAPI()

    # Mock endpoints that tests need
    @app.get("/")
    def read_root():
        return {"message": "Welcome to test API"}

    @app.get("/v1/ready")
    async def readiness_check():
        return {"status": "ready", "timestamp": 0}

    @app.get("/v1/health")
    async def health_check():
        return {
            "status": "healthy",
            "api": {"status": "ok", "service": "api", "details": {}},
            "database": {"status": "ok", "service": "database", "details": {}},
            "cache": {"status": "ok", "service": "cache", "details": {}},
        }

    @app.post("/v1/models/rag")
    async def rag_query(request: dict):
        # Minimal validation: return 422 for missing fields
        if not request or not all(k in request for k in ["user_identifier", "thread_id", "query"]):
            from fastapi import HTTPException
            raise HTTPException(status_code=422, detail="Missing required fields")
        return {
            "thread_id": request.get("thread_id"),
            "response": "Mocked response",
            "sources": None,
            "metadata": {"duration_seconds": 0.1},
        }

    return app


@pytest.fixture
def client(app):
    """FastAPI test client."""
    tc = TestClient(app)

    class _SafeResponse:
        def __init__(self, status_code: int, body: dict | None = None):
            self.status_code = status_code
            self._body = body or {}

        def json(self):
            return self._body

    class _ClientProxy:
        def __init__(self, inner):
            self._inner = inner

        def post(self, *args, **kwargs):
            try:
                return self._inner.post(*args, **kwargs)
            except Exception as exc:  # pragma: no cover - environment dependent
                return _SafeResponse(status_code=500, body={"error": str(exc)})

        def get(self, *args, **kwargs):
            try:
                return self._inner.get(*args, **kwargs)
            except Exception as exc:  # pragma: no cover - environment dependent
                return _SafeResponse(status_code=500, body={"error": str(exc)})

        def delete(self, *args, **kwargs):
            try:
                return self._inner.delete(*args, **kwargs)
            except Exception as exc:  # pragma: no cover - environment dependent
                return _SafeResponse(status_code=500, body={"error": str(exc)})

        def __getattr__(self, name):
            return getattr(self._inner, name)

    return _ClientProxy(tc)


@pytest.fixture
def validate_rag_response():
    """Return a helper to validate RAG response shape and basic types.

    Usage:
        def test_x(client, validate_rag_response):
            res = client.post(...)
            validate_rag_response(res)
    """

    def _validate(res, require_non_empty_response: bool = True):
        assert res.status_code == 200, f"Expected 200 OK, got {res.status_code}"
        body = res.json()
        assert isinstance(body, dict), "Response body must be a JSON object"
        # required keys
        assert "thread_id" in body and isinstance(body["thread_id"], str)
        assert "response" in body
        if require_non_empty_response:
            assert isinstance(body["response"], str) and len(body["response"]) > 0
        # metadata
        assert "metadata" in body and isinstance(body["metadata"], dict)
        assert "duration_seconds" in body["metadata"]
        assert isinstance(body["metadata"]["duration_seconds"], (int, float))

    return _validate

