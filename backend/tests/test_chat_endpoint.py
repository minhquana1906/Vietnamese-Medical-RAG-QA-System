from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)


def test_chat_endpoint_valid_message():
    """Kiểm tra gửi message hợp lệ"""
    payload = {
        "bot_id": "Meddy",
        "user_id": "user_1",
        "user_message": "Xin chào bác sĩ!",
        "is_sync_request": True
    }

    response = client.post("/chat/complete", json=payload)
    assert response.status_code in (200, 202)

    data = response.json()
    assert "status" in data
    assert data["status"] in ("completed", "processing")


def test_chat_endpoint_missing_message():
    """Kiểm tra lỗi khi thiếu user_message"""
    payload = {
        "bot_id": "Meddy",
        "user_id": "user_1",
        "is_sync_request": True
    }

    response = client.post("/chat/complete", json=payload)
    assert response.status_code == 422
