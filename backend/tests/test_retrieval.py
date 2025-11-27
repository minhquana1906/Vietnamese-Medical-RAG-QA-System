"""Tests for retrieval layer fallback and error handling (TC-RET-01 to TC-RET-05)."""
import uuid


def test_retrieval_no_results(client):
    """When retrieval yields no documents, system should still respond gracefully."""
    query_payload = {
        "user_identifier": "test-user",
        "thread_id": str(uuid.uuid4()),
        "query": "floru98h1h...",  # Nonsense query
    }

    res = client.post("/v1/models/rag", json=query_payload)
    assert res.status_code == 200
    body = res.json()
    assert "response" in body


def test_retrieval_malformed_query(client):
    """Malformed/ambiguous queries should return a helpful response (not crash)."""
    query_payload = {
        "user_identifier": "test-user",
        "thread_id": str(uuid.uuid4()),
        "query": "Điều đó có nguy hiểm không?",  # Ambiguous query
    }

    res = client.post("/v1/models/rag", json=query_payload)
    assert res.status_code == 200
    body = res.json()
    assert isinstance(body.get("response"), str)


def test_retrieval_clear_query(client):
    """Clear medical queries should return non-empty response text."""
    query_payload = {
        "user_identifier": "test-user",
        "thread_id": str(uuid.uuid4()),
        "query": "paracetamol tác dụng?",  # Clear medical query
    }

    res = client.post("/v1/models/rag", json=query_payload)
    assert res.status_code == 200
    body = res.json()
    assert isinstance(body.get("response"), str) and len(body.get("response")) > 0


def test_retrieval_special_characters(client):
    """Special character queries should be handled without error."""
    query_payload = {
        "user_identifier": "test-user",
        "thread_id": str(uuid.uuid4()),
        "query": "Bệnh tính-trạng (hỗ trợ?)? [Tìm kiếm] &)",
    }

    res = client.post("/v1/models/rag", json=query_payload)
    assert res.status_code == 200
    body = res.json()
    assert "response" in body
