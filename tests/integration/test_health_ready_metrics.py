import re


def test_root_info(client):
    resp = client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert "message" in data
    assert "version" in data
    # Routers list should include key prefixes
    assert any("/v1/rag" in r for r in data.get("routers", []))


def test_readiness_ok(client):
    resp = client.get("/v1/ready")
    assert resp.status_code == 200
    assert resp.json().get("status") in {"ready", "ok"}


def test_metrics_exposes_fastapi_counters(client):
    # Make an extra request to increment counters
    client.get("/")

    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    body = metrics.text
    # Check for common metric names exposed by the app
    assert "fastapi_requests_total" in body
    assert "fastapi_requests_duration_seconds" in body
    assert "fastapi_requests_in_progress" in body
