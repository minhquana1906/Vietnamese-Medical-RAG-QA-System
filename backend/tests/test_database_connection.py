import requests

def test_qdrant_connection():
    url = "http://qdrant_db:6333"
    try:
        response = requests.get(url, timeout=3)
        assert response.status_code == 200
        data = response.json()
        assert "qdrant" in data.get("title", "").lower()
    except requests.exceptions.RequestException:
        assert False, f"Cannot connect to Qdrant at {url}"