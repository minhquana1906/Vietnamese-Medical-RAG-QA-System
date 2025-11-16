from pathlib import Path
from typing import Optional
import yaml
from loguru import logger

# Path to models config file
CONFIG_PATH = Path(__file__).parent.parent / "config" / "models.yaml"

# Cached config (loaded once at startup)
_config_cache: Optional[dict] = None


def load_model_config() -> dict:
    """
    Load model configuration from YAML file.
    Returns cached config if already loaded.
    """
    global _config_cache

    if _config_cache is not None:
        return _config_cache

    if not CONFIG_PATH.exists():
        logger.error(f"Model config file not found: {CONFIG_PATH}")
        raise FileNotFoundError(f"Model config not found: {CONFIG_PATH}")

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        _config_cache = yaml.safe_load(f)

    logger.info(f"Loaded model config from {CONFIG_PATH}")
    return _config_cache


def get_generation_model() -> str:
    """Get active generation model HuggingFace repo ID."""
    config = load_model_config()
    return config["models"]["generation"]["active"]


def get_generation_fallback() -> str:
    """Get fallback generation model."""
    config = load_model_config()
    return config["models"]["generation"]["fallback"]


def get_embedding_model() -> str:
    """Get active embedding model HuggingFace repo ID."""
    config = load_model_config()
    return config["models"]["embedding"]["active"]


def get_embedding_triton_name() -> str:
    """Get Triton model name for embedding."""
    config = load_model_config()
    return config["models"]["embedding"]["triton_model_name"]


def get_embedding_fallback() -> str:
    """Get fallback embedding model."""
    config = load_model_config()
    return config["models"]["embedding"]["fallback"]


def get_reranking_model() -> str:
    """Get active reranking model HuggingFace repo ID."""
    config = load_model_config()
    return config["models"]["reranking"]["active"]


def get_reranking_triton_name() -> str:
    """Get Triton model name for reranking."""
    config = load_model_config()
    return config["models"]["reranking"]["triton_model_name"]


def get_reranking_fallback() -> str:
    """Get fallback reranking model."""
    config = load_model_config()
    return config["models"]["reranking"]["fallback"]


def get_guardrails_model() -> str:
    """Get active guardrails model HuggingFace repo ID."""
    config = load_model_config()
    return config["models"]["guardrails"]["active"]


def get_guardrails_triton_name() -> str:
    """Get Triton model name for guardrails."""
    config = load_model_config()
    return config["models"]["guardrails"]["triton_model_name"]


def get_guardrails_threshold() -> float:
    """Get safety threshold for guardrails."""
    config = load_model_config()
    return config["models"]["guardrails"]["threshold"]


def get_vllm_url() -> str:
    """Get vLLM server URL."""
    config = load_model_config()
    return config["serving"]["vllm_url"]


def get_triton_http_url() -> str:
    """Get Triton HTTP URL."""
    config = load_model_config()
    return config["serving"]["triton_http_url"]


def get_triton_grpc_url() -> str:
    """Get Triton gRPC URL."""
    config = load_model_config()
    return config["serving"]["triton_grpc_url"]


def reload_config():
    """Force reload config from file (useful for hot-reloading)."""
    global _config_cache
    _config_cache = None
    logger.info("Model config cache cleared, will reload on next access")
