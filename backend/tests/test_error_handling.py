def test_invalid_route(client):
    response = client.get("/nonexistent-route")
    assert response.status_code == 404
    assert "detail" in response.json()