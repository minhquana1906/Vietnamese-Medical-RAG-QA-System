from uuid import uuid4

from backend.src.schemas.schema import RAGQueryRequest


def test_rag_query_smoke(client):
    # Use a random thread_id; if it doesn't exist, service should still return a graceful message
    payload = {
        "user_identifier": "test-user",
        "thread_id": str(uuid4()),
        "query": "Triệu chứng điển hình của viêm phổi là gì?",
        "metadata": {"test": True},
    }

    resp = client.post("/v1/rag", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    # Ensure response schema-like fields are present
    assert data.get("thread_id") == payload["thread_id"]
    assert isinstance(data.get("response"), str)
    # sources may be None depending on pipeline
    assert "sources" in data
