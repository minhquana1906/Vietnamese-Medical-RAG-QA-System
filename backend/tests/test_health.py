def test_readiness(client):
    res = client.get("/v1/ready")
    assert res.status_code == 200
    body = res.json()
    assert body.get("status") == "ready"


def test_health_ok(client):
    res = client.get("/v1/health")
    assert res.status_code == 200
    body = res.json()
    assert body.get("status") in ["healthy", "degraded"]
    assert "api" in body and "database" in body and "cache" in body
