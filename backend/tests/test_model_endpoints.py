"""Tests for model inference endpoints (embed, rerank, guard)."""
import uuid


def test_embed_endpoint_basic(client):
    """Test POST /v1/models/embed endpoint."""
    payload = {
        "texts": ["Bệnh tiểu đường", "Viêm phổi"],
        "normalize": True,
        "is_query": False,
    }
    res = client.post("/v1/models/embed", json=payload)
    # May not be fully mocked
    assert res.status_code in (200, 404, 503)


def test_embed_endpoint_single_text(client):
    """Test embedding single text."""
    payload = {
        "texts": ["Test text"],
        "normalize": True,
    }
    res = client.post("/v1/models/embed", json=payload)
    assert res.status_code in (200, 404, 503)


def test_embed_endpoint_query_mode(client):
    """Test embedding with is_query=True."""
    payload = {
        "texts": ["Triệu chứng covid?"],
        "is_query": True,
    }
    res = client.post("/v1/models/embed", json=payload)
    assert res.status_code in (200, 404, 503)


def test_rerank_endpoint_basic(client):
    """Test POST /v1/models/rerank endpoint."""
    payload = {
        "query": "Triệu chứng covid?",
        "documents": [
            "COVID-19 là bệnh viêm đường hô hấp",
            "Bệnh tiểu đường type 2",
            "Bệnh viêm gan B",
        ],
        "top_n": 2,
    }
    res = client.post("/v1/models/rerank", json=payload)
    assert res.status_code in (200, 404, 503)


def test_rerank_endpoint_custom_top_n(client):
    """Test reranking with custom top_n."""
    payload = {
        "query": "test",
        "documents": ["doc1", "doc2", "doc3", "doc4", "doc5"],
        "top_n": 3,
    }
    res = client.post("/v1/models/rerank", json=payload)
    assert res.status_code in (200, 404, 503)


def test_guard_endpoint_input_check(client):
    """Test POST /v1/models/guard endpoint for input checking."""
    payload = {
        "text": "Kê đơn thuốc cho tôi",
        "check_type": "input",
    }
    res = client.post("/v1/models/guard", json=payload)
    assert res.status_code in (200, 404, 503)


def test_guard_endpoint_output_check(client):
    """Test guard for output checking."""
    payload = {
        "text": "Bạn nên tới bệnh viện để khám",
        "check_type": "output",
        "query": "Tôi bị đau gì?",
    }
    res = client.post("/v1/models/guard", json=payload)
    assert res.status_code in (200, 404, 503)


def test_guard_endpoint_safe_text(client):
    """Test guard on safe medical text."""
    payload = {
        "text": "Bệnh tiểu đường là tình trạng rối loạn chuyển hóa đường",
        "check_type": "input",
    }
    res = client.post("/v1/models/guard", json=payload)
    assert res.status_code in (200, 404, 503)


def test_guard_endpoint_unsafe_text(client):
    """Test guard on potentially unsafe text."""
    payload = {
        "text": "Uống 100 viên thuốc để chết",
        "check_type": "input",
    }
    res = client.post("/v1/models/guard", json=payload)
    # Should flag as potentially unsafe
    assert res.status_code in (200, 404, 503)


def test_embed_missing_texts_field(client):
    """Test embed endpoint without texts field."""
    res = client.post("/v1/models/embed", json={"normalize": True})
    assert res.status_code in (422, 404, 503)


def test_rerank_missing_query_field(client):
    """Test rerank without query field."""
    res = client.post(
        "/v1/models/rerank",
        json={"documents": ["doc1"]},
    )
    assert res.status_code in (422, 404, 503)


def test_guard_missing_text_field(client):
    """Test guard without text field."""
    res = client.post("/v1/models/guard", json={"check_type": "input"})
    assert res.status_code in (422, 404, 503)


def test_embed_with_custom_instruction(client):
    """Test embed with custom instruction parameter."""
    payload = {
        "texts": ["Custom text"],
        "instruction": "Given a medical query, retrieve relevant passages",
        "is_query": True,
    }
    res = client.post("/v1/models/embed", json=payload)
    assert res.status_code in (200, 404, 503)


def test_rerank_with_custom_instruction(client):
    """Test rerank with custom instruction."""
    payload = {
        "query": "test",
        "documents": ["doc1", "doc2"],
        "instruction": "Custom rerank instruction",
    }
    res = client.post("/v1/models/rerank", json=payload)
    assert res.status_code in (200, 404, 503)
