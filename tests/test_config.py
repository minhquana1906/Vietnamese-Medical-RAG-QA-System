def test_config_values():
    from backend.src import config

    assert hasattr(config, "LLM")
    assert hasattr(config, "EMBEDDING_MODEL")
    assert hasattr(config, "TEMPERATURE")
    assert hasattr(config, "MAX_TOKENS")

    assert isinstance(config.TEMPERATURE, (int, float))
    assert 0 <= config.TEMPERATURE <= 2
    assert isinstance(config.MAX_TOKENS, int)
    assert config.MAX_TOKENS > 0


def test_qdrant_config():
    from backend.src import config

    assert hasattr(config, "DEFAULT_COLLECTION_NAME")
    assert hasattr(config, "VECTOR_DIMENSION")
    assert hasattr(config, "TOP_K")

    assert isinstance(config.VECTOR_DIMENSION, int)
    assert config.VECTOR_DIMENSION > 0
    assert isinstance(config.TOP_K, int)
    assert config.TOP_K > 0


def test_chunking_config():
    from backend.src import config

    assert hasattr(config, "CHUNK_SIZE")
    assert hasattr(config, "CHUNK_OVERLAP")

    assert isinstance(config.CHUNK_SIZE, int)
    assert config.CHUNK_SIZE > 0
    assert isinstance(config.CHUNK_OVERLAP, int)
    assert config.CHUNK_OVERLAP >= 0
    assert config.CHUNK_OVERLAP < config.CHUNK_SIZE


def test_system_prompt():
    from backend.src import config

    assert hasattr(config, "SYSTEM_PROMPT")
    assert isinstance(config.SYSTEM_PROMPT, str)
    assert len(config.SYSTEM_PROMPT) > 0

    vietnamese_words = ["Bạn", "trả lời", "câu hỏi", "tài liệu"]
    assert any(word in config.SYSTEM_PROMPT for word in vietnamese_words)
