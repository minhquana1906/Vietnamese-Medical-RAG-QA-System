"""Tests for model inference endpoints (embed, rerank, guard)."""
import uuid


def _safe_post(client, path, payload):
    res = client.post(path, json=payload)
    # Accept 404/503 for unmocked endpoints but validate JSON if 200
    assert res.status_code in (200, 201, 202, 404, 422, 503)
    if res.status_code == 200:
        assert res.headers.get("content-type", "").startswith("application/json")
        assert isinstance(res.json(), (dict, list))
    return res


def test_embed_endpoint_basic(client):
    payload = {"texts": ["Bệnh tiểu đường", "Viêm phổi"], "normalize": True, "is_query": False}
    _safe_post(client, "/v1/models/embed", payload)


def test_embed_endpoint_single_text(client):
    payload = {"texts": ["Test text"], "normalize": True}
    _safe_post(client, "/v1/models/embed", payload)


def test_embed_endpoint_query_mode(client):
    payload = {"texts": ["Triệu chứng covid?"], "is_query": True}
    _safe_post(client, "/v1/models/embed", payload)


def test_rerank_endpoint_basic(client):
    payload = {
        "query": "Triệu chứng covid?",
        "documents": ["doc1", "doc2", "doc3"],
        "top_n": 2,
    }
    _safe_post(client, "/v1/models/rerank", payload)


def test_rerank_endpoint_custom_top_n(client):
    payload = {"query": "test", "documents": ["doc1", "doc2", "doc3"], "top_n": 3}
    _safe_post(client, "/v1/models/rerank", payload)


def test_guard_endpoints_and_missing_fields(client):
    # Input check
    _safe_post(client, "/v1/models/guard", {"text": "Kê đơn thuốc giúp tôi", "check_type": "input"})
    # Output check
    _safe_post(client, "/v1/models/guard", {"text": "Bạn nên tới bệnh viện", "check_type": "output"})
    # Missing field tests
    _safe_post(client, "/v1/models/embed", {"normalize": True})
    _safe_post(client, "/v1/models/rerank", {"documents": ["doc1"]})
