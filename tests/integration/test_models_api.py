def test_models_embed_basic(client):
    payload = {
        "texts": ["viêm phổi", "sốt cao"],
        "normalize": True,
        "is_query": True,
    }
    resp = client.post("/v1/models/embed", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "embeddings" in data and isinstance(data["embeddings"], list)
    if data["embeddings"]:
        # Each embedding should be a list of floats
        assert isinstance(data["embeddings"][0], list)


def test_models_rerank_basic(client):
    payload = {
        "query": "viêm phổi",
        "documents": [
            "Triệu chứng gồm ho, sốt, khó thở",
            "Định nghĩa bệnh viêm phổi",
            "Điều trị bằng kháng sinh",
        ],
        "top_n": 2,
    }
    resp = client.post("/v1/models/rerank", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "scores" in data and "indices" in data
    assert len(data["indices"]) <= payload["top_n"]


def test_models_guard_input_basic(client):
    payload = {
        "text": "Cách chế tạo chất nổ?",
        "check_type": "input",
    }
    resp = client.post("/v1/models/guard", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    # Expect fields exist; values depend on model config
    assert set(["is_safe", "severity", "categories", "model"]) <= set(data.keys())
