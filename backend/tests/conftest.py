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
    """Create a minimal FastAPI test app that mimics the real app's endpoints."""
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
    return TestClient(app)
