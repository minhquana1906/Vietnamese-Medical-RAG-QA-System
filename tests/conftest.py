import os
import sys
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

os.environ["TESTING"] = "true"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["CELERY_BROKER_URL"] = "redis://localhost:6379/0"
os.environ["CELERY_RESULT_BACKEND"] = "redis://localhost:6379/0"


@pytest.fixture
def client():
    from unittest.mock import patch

    with (
        patch("backend.src.models.init_db"),
        patch("backend.src.vectorize.create_collection"),
        patch("backend.src.main.setup_logger"),
    ):
        from backend.src.main import app

        return TestClient(app)


@pytest.fixture
def sample_chat_request():
    return {
        "bot_id": "test_bot",
        "user_id": "test_user",
        "user_message": "What are symptoms of fever?",
        "is_sync_request": True,
    }


@pytest.fixture
def mock_openai():
    mock_client = MagicMock()

    mock_embedding = MagicMock()
    mock_embedding.data = [MagicMock()]
    mock_embedding.data[0].embedding = [0.1] * 1536
    mock_client.embeddings.create.return_value = mock_embedding

    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock()]
    mock_completion.choices[0].message.content = "Test response"
    mock_client.chat.completions.create.return_value = mock_completion

    return mock_client
