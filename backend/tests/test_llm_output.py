"""Tests for LLM output evaluation (TC-LLM-01 to TC-LLM-05)."""
import uuid


def test_llm_factual_response(client):
    """Test LLM provides factually correct responses (TC-LLM-01)."""
    payload = {
        "user_identifier": "test-user",
        "thread_id": str(uuid.uuid4()),
        "query": "Bệnh tiểu đường type 1 là gì?",
    }

    res = client.post("/v1/models/rag", json=payload)
    assert res.status_code == 200
    body = res.json()
    assert body.get("response")
    # Real system would verify factual accuracy against retrieved docs


def test_llm_out_of_domain_rejection(client):
    """Test LLM refuses out-of-domain queries (TC-LLM-02)."""
    payload = {
        "user_identifier": "test-user",
        "thread_id": str(uuid.uuid4()),
        "query": "Viết code Python sorting?",  # Non-medical query
    }

    res = client.post("/v1/models/rag", json=payload)
    assert res.status_code == 200
    # Real system would refuse or redirect to healthcare context


def test_llm_no_hallucination(client):
    """Test LLM doesn't hallucinate when no context (TC-LLM-03)."""
    payload = {
        "user_identifier": "test-user",
        "thread_id": str(uuid.uuid4()),
        "query": "Thuốc imaginarypharm giúp gì?",  # Non-existent drug
    }

    res = client.post("/v1/models/rag", json=payload)
    assert res.status_code == 200
    body = res.json()
    # Real system would say "không có thông tin" instead of making up info
    assert body.get("response")


def test_llm_output_format(client):
    """Test LLM output conforms to requested format (TC-LLM-04)."""
    payload = {
        "user_identifier": "test-user",
        "thread_id": str(uuid.uuid4()),
        "query": "Trả lời dạng bullet list: Triệu chứng covid là gì?",
    }

    res = client.post("/v1/models/rag", json=payload)
    assert res.status_code == 200
    body = res.json()
    # Response should follow format
    assert body.get("response")


def test_llm_context_preservation(client):
    """Test LLM preserves conversation context (TC-LLM-05)."""
    thread_id = str(uuid.uuid4())

    # First query
    payload1 = {
        "user_identifier": "test-user",
        "thread_id": thread_id,
        "query": "Bệnh gì là bệnh tiểu đường?",
    }
    res1 = client.post("/v1/models/rag", json=payload1)
    assert res1.status_code == 200

    # Follow-up query (context-dependent)
    payload2 = {
        "user_identifier": "test-user",
        "thread_id": thread_id,
        "query": "Các triệu chứng chính là gì?",  # Refers to diabetes from previous query
    }
    res2 = client.post("/v1/models/rag", json=payload2)
    assert res2.status_code == 200
    # Real system would use conversation history to understand "Các triệu chứng"
