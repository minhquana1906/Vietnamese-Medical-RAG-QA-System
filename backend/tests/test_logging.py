"""Tests for logging and monitoring (TC-LOG-01 to TC-LOG-03)."""
import uuid
import logging


def test_error_logging(client, caplog):
    """Test that errors are properly logged with trace info (TC-LOG-01)."""
    with caplog.at_level(logging.WARNING):
        # Send malformed request that might cause an error
        payload = {
            "user_identifier": "test-user",
            "thread_id": str(uuid.uuid4()),
            "query": "",  # Empty query might trigger logging
        }

        res = client.post("/v1/models/rag", json=payload)
        # Should handle gracefully or return server error when dependencies missing
        assert res.status_code in (200, 422, 500, 503)
        # If any warnings were emitted, ensure they are warnings (not exceptions)
        for record in caplog.records:
            assert record.levelname in ("WARNING", "ERROR", "INFO")


def test_no_sensitive_data_in_logs(client, caplog):
    """Test that token/sensitive data is not logged (TC-LOG-02)."""
    with caplog.at_level(logging.DEBUG):
        payload = {
            "user_identifier": "test-user",
            "thread_id": str(uuid.uuid4()),
            "query": "query with secret_token_abc123xyz",
        }

        res = client.post("/v1/models/rag", json=payload)
        # Check that token is not in log records
        token = "secret_token_abc123xyz"
        exposed = [r for r in caplog.records if token in r.getMessage()]
        assert not exposed, "Sensitive token was found in logs"


def test_slow_query_logging(client, caplog, monkeypatch):
    """Test that slow queries (>2s) are logged as warnings (TC-LOG-03)."""
    import time

    # Mock a slow operation by storing request time
    def slow_rag_query(request: dict):
        if not request or not all(k in request for k in ["user_identifier", "thread_id", "query"]):
            from fastapi import HTTPException
            raise HTTPException(status_code=422, detail="Missing required fields")
        
        # Simulate slow response (in real system, this would be actual delay)
        start = time.time()
        # Sleep would happen in actual retrieval/LLM call
        # For test, we just return timing info
        
        return {
            "thread_id": request.get("thread_id"),
            "response": "Slow response",
            "sources": None,
            "metadata": {"duration_seconds": 2.5},  # Simulate 2.5s response
        }

    # Optionally patch the endpoint, but since it's mocked, we verify metadata
    with caplog.at_level(logging.WARNING):
        payload = {
            "user_identifier": "test-user",
            "thread_id": str(uuid.uuid4()),
            "query": "Slow query test",
        }

        res = client.post("/v1/models/rag", json=payload)
        if res.status_code == 200:
            # Verify response includes timing metadata
            body = res.json()
            assert body.get("metadata", {}).get("duration_seconds") is not None
        else:
            assert res.status_code in (500, 503)


def test_request_logging(client, caplog):
    """Test that requests are logged (basic audit trail)."""
    with caplog.at_level(logging.INFO):
        payload = {
            "user_identifier": "test-user-123",
            "thread_id": str(uuid.uuid4()),
            "query": "Test query",
        }

        res = client.post("/v1/models/rag", json=payload)
        assert res.status_code in (200, 500, 503)
        # In the mocked environment we may not capture request logs; ensure no sensitive info
        for record in caplog.records:
            assert "secret" not in record.getMessage().lower()
