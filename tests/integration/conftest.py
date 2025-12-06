import os
import pytest
from fastapi.testclient import TestClient

# Import the FastAPI app from the backend
from backend.src.main import app


@pytest.fixture(scope="session")
def client():
    """In-process ASGI client hitting the real app and services.

    Assumes environment variables and external services are already configured
    and reachable (DB, Redis, Qdrant, Elasticsearch, vLLM, etc.).
    """
    with TestClient(app) as test_client:
        yield test_client
