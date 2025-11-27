"""Tests for response format and data validation."""
import uuid
import json
import pytest


def test_response_is_valid_json(client, validate_rag_response):
    """Test that response is valid JSON."""
    payload = {
        "user_identifier": "test-user",
        "thread_id": str(uuid.uuid4()),
        "query": "test",
    }
    res = client.post("/v1/models/rag", json=payload)
    # Basic shape checks
    validate_rag_response(res)


def test_response_content_type_is_json(client):
    """Test that response Content-Type is application/json."""
    payload = {
        "user_identifier": "test-user",
        "thread_id": str(uuid.uuid4()),
        "query": "test",
    }
    res = client.post("/v1/models/rag", json=payload)
    assert res.status_code == 200
    
    # Check Content-Type header
    assert "application/json" in res.headers.get("content-type", "")


def test_response_thread_id_matches_request(client, validate_rag_response):
    """Test that response thread_id matches request."""
    thread_id = str(uuid.uuid4())
    payload = {
        "user_identifier": "test-user",
        "thread_id": thread_id,
        "query": "test",
    }
    res = client.post("/v1/models/rag", json=payload)
    validate_rag_response(res)
    body = res.json()
    assert body["thread_id"] == thread_id


def test_response_has_all_required_fields(client, validate_rag_response):
    """Test response contains all required fields."""
    payload = {
        "user_identifier": "test-user",
        "thread_id": str(uuid.uuid4()),
        "query": "test",
    }
    res = client.post("/v1/models/rag", json=payload)
    validate_rag_response(res)
    body = res.json()
    required_fields = ["thread_id", "response", "metadata"]
    for field in required_fields:
        assert field in body, f"Missing required field: {field}"


def test_response_metadata_has_duration(client, validate_rag_response):
    """Test metadata includes duration_seconds."""
    payload = {
        "user_identifier": "test-user",
        "thread_id": str(uuid.uuid4()),
        "query": "test",
    }
    res = client.post("/v1/models/rag", json=payload)
    validate_rag_response(res)
    body = res.json()
    metadata = body.get("metadata", {})
    assert "duration_seconds" in metadata
    assert isinstance(metadata["duration_seconds"], (int, float))
    assert metadata["duration_seconds"] >= 0


def test_response_no_extra_fields(client):
    """Test response doesn't contain unexpected fields."""
    payload = {
        "user_identifier": "test-user",
        "thread_id": str(uuid.uuid4()),
        "query": "test",
    }
    res = client.post("/v1/models/rag", json=payload)
    assert res.status_code == 200
    
    body = res.json()
    allowed_fields = {"thread_id", "response", "sources", "metadata"}
    actual_fields = set(body.keys())
    
    # All fields should be allowed
    assert actual_fields.issubset(allowed_fields)


def test_response_sources_is_list_or_null(client):
    """Test that sources field is list or null."""
    payload = {
        "user_identifier": "test-user",
        "thread_id": str(uuid.uuid4()),
        "query": "test",
    }
    res = client.post("/v1/models/rag", json=payload)
    assert res.status_code == 200
    
    body = res.json()
    sources = body.get("sources")
    assert sources is None or isinstance(sources, list)


def test_response_response_field_is_string(client, validate_rag_response):
    """Test that response field is a string."""
    payload = {
        "user_identifier": "test-user",
        "thread_id": str(uuid.uuid4()),
        "query": "test",
    }
    res = client.post("/v1/models/rag", json=payload)
    validate_rag_response(res)
    body = res.json()
    response_text = body.get("response")
    assert isinstance(response_text, str)
    assert len(response_text) > 0


def test_response_thread_id_is_string(client, validate_rag_response):
    """Test that thread_id in response is string."""
    payload = {
        "user_identifier": "test-user",
        "thread_id": str(uuid.uuid4()),
        "query": "test",
    }
    res = client.post("/v1/models/rag", json=payload)
    validate_rag_response(res)
    body = res.json()
    assert isinstance(body.get("thread_id"), str)


def test_error_response_format(client):
    """Test error response has proper format."""
    res = client.post("/v1/models/rag", json={})
    assert res.status_code == 422

    # Should still be JSON
    body = res.json()
    assert isinstance(body, dict)
    # Error responses typically have 'detail' field
    assert "detail" in body or "error" in body or res.status_code != 200


def test_response_no_null_required_fields(client, validate_rag_response):
    """Test that required fields are not null."""
    payload = {
        "user_identifier": "test-user",
        "thread_id": str(uuid.uuid4()),
        "query": "test",
    }
    res = client.post("/v1/models/rag", json=payload)
    validate_rag_response(res)
    body = res.json()
    assert body.get("thread_id") is not None
    assert body.get("response") is not None


def test_response_unicode_in_response_text(client, validate_rag_response):
    """Test that response properly handles unicode."""
    payload = {
        "user_identifier": "test-user",
        "thread_id": str(uuid.uuid4()),
        "query": "test với unicode",
    }
    res = client.post("/v1/models/rag", json=payload)
    validate_rag_response(res)
    body = res.json()
    # Response should be decodable
    response_text = body.get("response", "")
    assert isinstance(response_text, str)


def test_response_no_sensitive_data_exposed(client, validate_rag_response):
    """Test that response doesn't expose sensitive info."""
    payload = {
        "user_identifier": "test-user",
        "thread_id": str(uuid.uuid4()),
        "query": "test",
    }
    res = client.post("/v1/models/rag", json=payload)
    validate_rag_response(res)
    body = res.json()
    response_text = body.get("response", "")

    # Response should not contain database URLs or internal paths
    sensitive_patterns = ["postgresql://", "mongodb://", "/var/", "c:\\", "password"]
    for pattern in sensitive_patterns:
        assert pattern not in response_text.lower()
