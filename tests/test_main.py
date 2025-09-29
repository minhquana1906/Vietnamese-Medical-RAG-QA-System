from unittest.mock import patch


def test_root_endpoint(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Welcome" in response.json()["message"]


def test_readiness_check(client):
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


class TestChatEndpoints:
    def test_chat_complete_missing_message(self, client):
        response = client.post("/chat/complete", json={"bot_id": "test"})
        assert response.status_code == 422  # Validation error

    @patch("backend.src.main.message_handler_task")
    def test_chat_complete_sync(self, mock_task, client, sample_chat_request):
        mock_task.return_value = "Test response"

        response = client.post("/chat/complete", json=sample_chat_request)
        assert response.status_code == 200
        assert response.json()["status"] == "completed"
        assert response.json()["response"] == "Test response"

    @patch("backend.src.main.message_handler_task")
    def test_chat_complete_async(self, mock_task, client, sample_chat_request):
        mock_result = type("AsyncResult", (), {"id": "test-task-123"})()
        mock_task.delay.return_value = mock_result

        request = {**sample_chat_request, "is_sync_request": False}
        response = client.post("/chat/complete", json=request)

        assert response.status_code == 200
        assert response.json()["status"] == "processing"
        assert response.json()["task_id"] == "test-task-123"


class TestCollectionEndpoints:
    @patch("backend.src.main.create_collection")
    def test_create_collection(self, mock_create, client):
        mock_create.return_value = "Success"

        response = client.post("/collections/create")
        assert response.status_code == 200
        assert response.json()["status"] == "Success"


class TestDocumentEndpoints:
    @patch("backend.src.main.chunk_and_index_document")
    @patch("backend.src.main.insert_document")
    def test_insert_document(self, mock_insert, mock_chunk, client):
        mock_doc = type("Document", (), {"id": 123})()
        mock_insert.return_value = mock_doc

        response = client.post("/documents/create", params={"title": "Test Doc", "content": "Test content"})

        assert response.status_code == 200
        assert response.json()["document_id"] == "123"
        assert "indexing started" in response.json()["status"]
