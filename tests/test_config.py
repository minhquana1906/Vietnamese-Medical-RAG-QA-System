def test_config_values():
    """
    Test BackendSettings configuration values.

    Updated to use Pydantic Settings pattern.
    """
    from backend.src.config import get_backend_settings

    settings = get_backend_settings()

    # Check LLM model settings
    assert hasattr(settings, "openai_model")
    assert hasattr(settings, "openai_embedding_model")
    assert hasattr(settings, "temperature")
    assert hasattr(settings, "max_tokens")

    # Validate temperature range
    assert isinstance(settings.temperature, (int, float))
    assert 0 <= settings.temperature <= 2

    # Validate max_tokens
    assert isinstance(settings.max_tokens, int)
    assert settings.max_tokens > 0


def test_qdrant_config():
    """
    Test Qdrant vector database configuration.

    Updated to use Pydantic Settings pattern.
    """
    from backend.src.config import get_backend_settings

    settings = get_backend_settings()

    # Check Qdrant settings
    assert hasattr(settings, "default_collection_name")
    assert hasattr(settings, "vector_dimension")
    assert hasattr(settings, "top_k")

    # Validate vector dimension
    assert isinstance(settings.vector_dimension, int)
    assert settings.vector_dimension > 0

    # Validate top_k
    assert isinstance(settings.top_k, int)
    assert settings.top_k > 0


def test_chunking_config():
    """
    Test document chunking configuration.

    Updated to use Pydantic Settings pattern.
    """
    from backend.src.config import get_backend_settings

    settings = get_backend_settings()

    # Check chunking settings
    assert hasattr(settings, "chunk_size")
    assert hasattr(settings, "chunk_overlap")

    # Validate chunk size
    assert isinstance(settings.chunk_size, int)
    assert settings.chunk_size > 0

    # Validate chunk overlap
    assert isinstance(settings.chunk_overlap, int)
    assert settings.chunk_overlap >= 0
    assert settings.chunk_overlap < settings.chunk_size


def test_system_prompt():
    """
    Test system prompt configuration.

    Updated to use Pydantic Settings pattern.
    """
    from backend.src.config import get_backend_settings

    settings = get_backend_settings()

    # Check system prompt
    assert hasattr(settings, "system_prompt")
    assert isinstance(settings.system_prompt, str)
    assert len(settings.system_prompt) > 0

    # Verify Vietnamese content
    vietnamese_words = ["Bạn", "trả lời", "câu hỏi", "tài liệu"]
    assert any(word in settings.system_prompt for word in vietnamese_words)
