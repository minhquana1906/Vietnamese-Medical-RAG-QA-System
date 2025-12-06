"""
Integration Test Configuration

These tests hit the REAL backend service running at http://localhost:8000
(not an in-process test client). This approach:
- Tests the actual deployed system
- Avoids Docker networking issues
- Validates end-to-end integration with real services

Prerequisites:
- Backend service must be running: cd backend && docker compose up -d
- All external services must be accessible (PostgreSQL, Redis, etc.)
"""

import os
import pytest
import httpx


@pytest.fixture(scope="session")
def backend_url():
    """Backend API base URL"""
    return os.getenv("BACKEND_URL", "http://localhost:8000")


@pytest.fixture(scope="session")
def client(backend_url):
    """HTTP client for integration tests against real backend service"""
    with httpx.Client(base_url=backend_url, timeout=30.0) as client:
        # Verify backend is reachable
        try:
            response = client.get("/v1/health")
            if response.status_code not in (200, 503):
                pytest.skip(f"Backend service not available: {response.status_code}")
        except Exception as e:
            pytest.skip(f"Backend service not reachable: {e}")

        yield client
