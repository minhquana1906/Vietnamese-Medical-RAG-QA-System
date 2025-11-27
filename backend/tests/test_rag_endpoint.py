import uuid
from fastapi import HTTPException


def test_rag_validation_missing_fields(client):
    """Test that RAG endpoint returns 422 for missing fields (TC-CHAT-04)."""
    res = client.post("/v1/models/rag", json={})
    assert res.status_code == 422


def test_rag_validation_missing_user_identifier(client):
    """Test that RAG endpoint rejects request without user_identifier."""
    payload = {
        "thread_id": str(uuid.uuid4()),
        "query": "Triệu chứng covid?",
    }
    res = client.post("/v1/models/rag", json=payload)
    assert res.status_code == 422


def test_rag_basic_flow(client):
    """Test successful RAG query flow (TC-CHAT-01)."""
    payload = {
        "user_identifier": "test-user",
        "thread_id": str(uuid.uuid4()),
        "query": "Triệu chứng covid?",
    }

    res = client.post("/v1/models/rag", json=payload)
    assert res.status_code == 200
    body = res.json()
    assert "thread_id" in body
    assert "response" in body
    assert body["response"] == "Mocked response"


def test_rag_unicode_query(client):
    """Test that RAG endpoint accepts unicode queries (TC-CHAT-06)."""
    payload = {
        "user_identifier": "test-user",
        "thread_id": str(uuid.uuid4()),
        "query": "Triệu chứng covid 😷? Cách điều trị?",
    }

    res = client.post("/v1/models/rag", json=payload)
    assert res.status_code == 200
    body = res.json()
    assert body["response"]
