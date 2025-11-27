def test_readiness(client):
    res = client.get("/v1/ready")
    assert res.status_code == 200
    body = res.json()
    assert isinstance(body, dict)
    assert body.get("status") == "ready"
    assert "timestamp" in body


def test_health_ok(client):
    res = client.get("/v1/health")
    assert res.status_code == 200
    body = res.json()
    assert body.get("status") in ["healthy", "degraded"]
    # Ensure subcomponents are present and have expected structure
    for key in ("api", "database", "cache"):
        assert key in body and isinstance(body[key], dict)
        assert "status" in body[key]
