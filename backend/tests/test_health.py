from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)

def test_health_check():
    """Kiểm tra endpoint /ready phản hồi đúng"""
    response = client.get("/ready")
    assert response.status_code == 200

    data = response.json()
    # Kiểm tra cấu trúc phản hồi
    assert isinstance(data, dict)
    assert "status" in data
    assert "timestamp" in data

    # Kiểm tra giá trị trạng thái
    assert data["status"] in ("ready", "ok", "healthy")
    assert isinstance(data["timestamp"], (int, float))
