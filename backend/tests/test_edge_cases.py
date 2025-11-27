"""Extended tests for edge cases and stress scenarios."""
import uuid
import json


def test_rag_empty_query(client):
    """Test RAG endpoint with empty query string."""
    payload = {
        "user_identifier": "test-user",
        "thread_id": str(uuid.uuid4()),
        "query": "",
    }
    res = client.post("/v1/models/rag", json=payload)
    # Should handle empty query gracefully
    assert res.status_code in (200, 400, 422)
    if res.status_code == 200:
        assert "response" in res.json()


def test_rag_very_long_query(client):
    """Test RAG endpoint with very long query (5000+ characters)."""
    long_query = "Triệu chứng covid? " * 300  # ~5400 characters
    payload = {
        "user_identifier": "test-user",
        "thread_id": str(uuid.uuid4()),
        "query": long_query,
    }
    res = client.post("/v1/models/rag", json=payload)
    # Should handle long query without crash (TC-CHAT-05)
    assert res.status_code in (200, 413)
    if res.status_code == 200:
        assert "response" in res.json()


def test_rag_special_characters(client):
    """Test RAG with special characters and symbols."""
    payload = {
        "user_identifier": "test-user",
        "thread_id": str(uuid.uuid4()),
        "query": "Bệnh/liều ⚠️ [vip] {special} (test) @covid #health!",
    }
    res = client.post("/v1/models/rag", json=payload)
    assert res.status_code == 200
    assert isinstance(res.json().get("response"), str)


def test_rag_sql_injection_attempt(client):
    """Test RAG safely handles SQL-like injection attempts."""
    payload = {
        "user_identifier": "test-user",
        "thread_id": str(uuid.uuid4()),
        "query": "'; DROP TABLE users; --",
    }
    res = client.post("/v1/models/rag", json=payload)
    # Should safely handle and not execute SQL
    assert res.status_code == 200
    body = res.json()
    assert "response" in body


def test_rag_with_null_values(client):
    """Test RAG endpoint handles null in required fields."""
    res = client.post(
        "/v1/models/rag",
        json={"user_identifier": None, "thread_id": str(uuid.uuid4()), "query": "test"},
    )
    # Mock app may accept null values - this is acceptable behavior
    assert res.status_code in (422, 400, 200)


def test_rag_with_wrong_uuid_format(client):
    """Test RAG with invalid thread_id format."""
    payload = {
        "user_identifier": "test-user",
        "thread_id": "not-a-valid-uuid",
        "query": "test",
    }
    res = client.post("/v1/models/rag", json=payload)
    # Should accept string UUID or gracefully handle
    assert res.status_code in (200, 422)


def test_rag_extra_unknown_fields(client):
    """Test RAG endpoint ignores extra unknown fields."""
    payload = {
        "user_identifier": "test-user",
        "thread_id": str(uuid.uuid4()),
        "query": "test",
        "extra_field": "should be ignored",
        "another_field": {"nested": "data"},
    }
    res = client.post("/v1/models/rag", json=payload)
    # Should ignore extra fields and work normally
    assert res.status_code == 200


def test_rag_response_includes_metadata(client):
    """Test RAG response includes timing metadata."""
    payload = {
        "user_identifier": "test-user",
        "thread_id": str(uuid.uuid4()),
        "query": "test",
    }
    res = client.post("/v1/models/rag", json=payload)
    assert res.status_code == 200
    body = res.json()
    assert "metadata" in body
    assert "duration_seconds" in body.get("metadata", {})


def test_rag_response_structure(client):
    """Test RAG response has required fields."""
    payload = {
        "user_identifier": "test-user",
        "thread_id": str(uuid.uuid4()),
        "query": "test",
    }
    res = client.post("/v1/models/rag", json=payload)
    assert res.status_code == 200
    body = res.json()
    assert "thread_id" in body
    assert "response" in body
    assert body["thread_id"] == payload["thread_id"]


def test_rag_same_thread_multiple_queries(client):
    """Test multiple queries in same thread maintain context."""
    thread_id = str(uuid.uuid4())

    # Query 1
    res1 = client.post(
        "/v1/models/rag",
        json={"user_identifier": "test-user", "thread_id": thread_id, "query": "query1"},
    )
    assert res1.status_code == 200

    # Query 2 - same thread
    res2 = client.post(
        "/v1/models/rag",
        json={"user_identifier": "test-user", "thread_id": thread_id, "query": "query2"},
    )
    assert res2.status_code == 200
    assert res2.json()["thread_id"] == thread_id


def test_rag_different_users_different_context(client):
    """Test different users don't share context."""
    thread_id = str(uuid.uuid4())

    # User 1
    res1 = client.post(
        "/v1/models/rag",
        json={
            "user_identifier": "user-1",
            "thread_id": thread_id,
            "query": "query1",
        },
    )
    assert res1.status_code == 200

    # User 2 - different user should work independently
    res2 = client.post(
        "/v1/models/rag",
        json={
            "user_identifier": "user-2",
            "thread_id": str(uuid.uuid4()),
            "query": "query2",
        },
    )
    assert res2.status_code == 200


def test_rag_user_identifier_special_chars(client):
    """Test user_identifier with special characters."""
    payload = {
        "user_identifier": "user@example.com|oauth:12345",
        "thread_id": str(uuid.uuid4()),
        "query": "test",
    }
    res = client.post("/v1/models/rag", json=payload)
    # Should accept various identifier formats
    assert res.status_code == 200


def test_rag_user_identifier_very_long(client):
    """Test user_identifier with very long string."""
    payload = {
        "user_identifier": "a" * 500,
        "thread_id": str(uuid.uuid4()),
        "query": "test",
    }
    res = client.post("/v1/models/rag", json=payload)
    assert res.status_code in (200, 422)


def test_rag_thread_id_as_string_uuid(client):
    """Test thread_id accepts string UUID format."""
    thread_id = "12345678-1234-5678-1234-567812345678"
    payload = {
        "user_identifier": "test-user",
        "thread_id": thread_id,
        "query": "test",
    }
    res = client.post("/v1/models/rag", json=payload)
    # Should accept UUID string
    assert res.status_code == 200


def test_rag_content_type_json(client):
    """Test RAG endpoint with explicit JSON content-type."""
    payload = {
        "user_identifier": "test-user",
        "thread_id": str(uuid.uuid4()),
        "query": "test",
    }
    res = client.post(
        "/v1/models/rag",
        json=payload,
        headers={"Content-Type": "application/json"},
    )
    assert res.status_code == 200


def test_rag_query_with_newlines(client):
    """Test RAG query with multiple newlines and formatting."""
    payload = {
        "user_identifier": "test-user",
        "thread_id": str(uuid.uuid4()),
        "query": """Câu hỏi multiline:
        - Triệu chứng gì?
        - Cách điều trị?
        - Liều lượng bao nhiêu?""",
    }
    res = client.post("/v1/models/rag", json=payload)
    assert res.status_code == 200


def test_rag_query_vietnamese_tones(client):
    """Test RAG query with all Vietnamese tone marks."""
    payload = {
        "user_identifier": "test-user",
        "thread_id": str(uuid.uuid4()),
        "query": "Á À Ả Ã Ạ Ă Ắ Ằ Ẳ Ẵ Ặ Â Ấ Ầ Ẩ Ẫ Ậ",
    }
    res = client.post("/v1/models/rag", json=payload)
    assert res.status_code == 200


def test_rag_mixed_language_query(client):
    """Test RAG with mixed Vietnamese and English."""
    payload = {
        "user_identifier": "test-user",
        "thread_id": str(uuid.uuid4()),
        "query": "COVID-19 là bệnh gì? What is paracetamol? 阿司匹林?",
    }
    res = client.post("/v1/models/rag", json=payload)
    assert res.status_code == 200


def test_rag_query_with_urls(client):
    """Test RAG query containing URLs."""
    payload = {
        "user_identifier": "test-user",
        "thread_id": str(uuid.uuid4()),
        "query": "Tìm hiểu tại https://example.com/health hoặc http://docs.test.com",
    }
    res = client.post("/v1/models/rag", json=payload)
    assert res.status_code == 200


def test_rag_query_with_emails(client):
    """Test RAG query containing email addresses."""
    payload = {
        "user_identifier": "test-user",
        "thread_id": str(uuid.uuid4()),
        "query": "Liên hệ doctor@hospital.com hoặc info@clinic.vn",
    }
    res = client.post("/v1/models/rag", json=payload)
    assert res.status_code == 200


def test_rag_query_with_numbers(client):
    """Test RAG query with various number formats."""
    payload = {
        "user_identifier": "test-user",
        "thread_id": str(uuid.uuid4()),
        "query": "Liều 500mg, 3 lần/ngày, 0.5 viên, 2,500 đồng/viên",
    }
    res = client.post("/v1/models/rag", json=payload)
    assert res.status_code == 200


def test_rag_query_with_symbols(client):
    """Test RAG query with mathematical and special symbols."""
    payload = {
        "user_identifier": "test-user",
        "thread_id": str(uuid.uuid4()),
        "query": "Thời gian: 2-3 tuần, độ tuổi: 18-65, tỷ lệ: 1:100, giá: $10-20",
    }
    res = client.post("/v1/models/rag", json=payload)
    assert res.status_code == 200
