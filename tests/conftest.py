import os
import sys
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# Set environment variables for testing
os.environ["TESTING"] = "true"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

# OpenAI & Cohere API keys (mock values for testing)
os.environ["OPENAI_API_KEY"] = "test-openai-key"
os.environ["COHERE_API_KEY"] = "test-cohere-key"

# Redis configuration
os.environ["REDIS_HOST"] = "localhost"
os.environ["REDIS_PORT"] = "6379"

# Celery configuration
os.environ["CELERY_BROKER_URL"] = "redis://localhost:6379/0"
os.environ["CELERY_RESULT_BACKEND"] = "redis://localhost:6379/0"

# Qdrant configuration
os.environ["QDRANT_HOST"] = "localhost"
os.environ["QDRANT_PORT"] = "6333"

# PostgreSQL configuration (for testing)
os.environ["POSTGRES_USER"] = "test_user"
os.environ["POSTGRES_PASSWORD"] = "test_password"
os.environ["POSTGRES_DB"] = "test_db"
os.environ["POSTGRES_HOST"] = "localhost"
os.environ["POSTGRES_PORT"] = "5432"


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
