"""
RAG-focused Logging Configuration

This module configures structured logging optimized for RAG pipeline tracking.
Key information logged:
- Query enhancement results
- Guardrails validation (pass/reject with category)
- Embedding generation (dimension, success/fail)
- Retrieval results (count, cache hit/miss)
- Reranking results (top-k chunks with scores, truncated content)
- History summarization stats
- Response generation with timing
"""

import sys
import time
from typing import Any, Dict, List, Optional

from loguru import logger

from .setup import get_backend_settings

settings = get_backend_settings()


# ============= RAG LOGGING HELPERS =============


def truncate_text(text: str, max_length: int = 100) -> str:
    """Truncate text for logging display."""
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."


def format_duration(start_time: float) -> str:
    """Format duration in human-readable format."""
    duration = time.time() - start_time
    if duration < 1:
        return f"{duration * 1000:.0f}ms"
    return f"{duration:.2f}s"


class RAGLogger:
    """
    Structured logger for RAG pipeline events.

    Provides consistent formatting for key RAG events:
    - Query processing
    - Guardrails validation
    - Embedding generation
    - Retrieval and reranking
    - Response generation
    """

    @staticmethod
    def log_request_start(user_id: str, thread_id: str, query: str) -> float:
        """Log RAG request start and return start time."""
        logger.info(
            f"[RAG] ▶ Request | user={user_id} | thread={thread_id[:8]}... | query={truncate_text(query, 80)}"
        )
        return time.time()

    @staticmethod
    def log_query_enhancement(original: str, enhanced: str):
        """Log query enhancement result."""
        if original.strip() == enhanced.strip():
            logger.debug(f"[RAG] 📝 Query unchanged")
        else:
            logger.info(
                f"[RAG] 📝 Query enhanced | original={truncate_text(original, 60)} | enhanced={truncate_text(enhanced, 60)}"
            )

    @staticmethod
    def log_route_detection(route: str):
        """Log detected route."""
        emoji = "🏥" if route == "medical" else "💬"
        logger.info(f"[RAG] {emoji} Route | {route}")

    @staticmethod
    def log_guardrails_input(
        is_valid: bool, category: Optional[str] = None, severity: Optional[str] = None
    ):
        """Log input guardrails validation result."""
        if is_valid:
            logger.info(f"[RAG] 🛡️ Guardrails input | ✅ PASS")
        else:
            logger.warning(
                f"[RAG] 🛡️ Guardrails input | ❌ REJECT | category={category} | severity={severity}"
            )

    @staticmethod
    def log_guardrails_output(
        is_valid: bool,
        category: Optional[str] = None,
        severity: Optional[str] = None,
        attempt: int = 1,
    ):
        """Log output guardrails validation result."""
        if is_valid:
            logger.info(f"[RAG] 🛡️ Guardrails output | ✅ PASS")
        else:
            logger.warning(
                f"[RAG] 🛡️ Guardrails output | ❌ REJECT | category={category} | severity={severity} | attempt={attempt}"
            )

    @staticmethod
    def log_embedding(
        success: bool,
        dimension: int = 0,
        is_query: bool = True,
        cache_hit: bool = False,
    ):
        """Log embedding generation result."""
        text_type = "query" if is_query else "document"
        cache_status = "HIT" if cache_hit else "MISS"

        if success:
            logger.success(
                f"[RAG] 🔢 Embedding | ✅ {text_type} | dim={dimension} | cache={cache_status}"
            )
        else:
            logger.error(f"[RAG] 🔢 Embedding | ❌ FAILED | type={text_type}")

    @staticmethod
    def log_retrieval(
        vector_count: int, keyword_count: int, fused_count: int, cache_hit: bool = False
    ):
        """Log hybrid search retrieval results."""
        cache_status = "HIT" if cache_hit else "MISS"
        logger.info(
            f"[RAG] 🔍 Retrieval | vector={vector_count} | keyword={keyword_count} | fused={fused_count} | cache={cache_status}"
        )

    @staticmethod
    def log_rerank_results(
        reranked_docs: List[Dict[str, Any]],
        top_n: int = 5,
        max_content_length: int = 80,
    ):
        """Log reranking results with scores and truncated content."""
        if not reranked_docs:
            logger.warning("[RAG] ⚡ Rerank | No documents to rerank")
            return

        logger.info(
            f"[RAG] ⚡ Rerank | top_n={min(top_n, len(reranked_docs))} results:"
        )

        for i, doc in enumerate(reranked_docs[:top_n]):
            score = doc.get("relevance_score", 0)
            # Get content from document
            doc_data = doc.get("document", doc)
            title = doc_data.get("title", "N/A")
            content = doc_data.get("content", "")

            logger.info(
                f"  #{i+1} | score={score:.4f} | title={truncate_text(title, 40)} | content={truncate_text(content, max_content_length)}"
            )

    @staticmethod
    def log_history_summary(
        original_count: int,
        summarized_count: int,
        original_tokens: int,
        new_tokens: int,
    ):
        """Log history summarization stats."""
        if original_count == summarized_count:
            logger.debug(
                f"[RAG] 📋 History | no summarization needed | msgs={original_count}"
            )
        else:
            reduction = (
                ((original_tokens - new_tokens) / original_tokens * 100)
                if original_tokens > 0
                else 0
            )
            logger.info(
                f"[RAG] 📋 History | msgs={original_count}→{summarized_count} | tokens=~{original_tokens}→~{new_tokens} | reduced={reduction:.0f}%"
            )

    @staticmethod
    def log_generation(
        success: bool,
        response_length: int = 0,
        model: str = "",
        use_web_search: bool = False,
    ):
        """Log response generation result."""
        source = "web_search" if use_web_search else "rag"
        if success:
            logger.success(
                f"[RAG] 🤖 Generation | ✅ {source} | length={response_length} chars | model={model}"
            )
        else:
            logger.error(f"[RAG] 🤖 Generation | ❌ FAILED | source={source}")

    @staticmethod
    def log_request_complete(start_time: float, success: bool = True):
        """Log RAG request completion with timing."""
        duration = format_duration(start_time)
        status = "✅ SUCCESS" if success else "❌ FAILED"
        logger.info(f"[RAG] ◀ Complete | {status} | duration={duration}")

    @staticmethod
    def log_cache_operation(
        cache_type: str, operation: str, hit: bool = True, key_preview: str = ""
    ):
        """Log cache operation (for detailed debugging)."""
        status = "HIT" if hit else "MISS"
        logger.debug(
            f"[CACHE] {cache_type} | {operation} | {status} | key={truncate_text(key_preview, 40)}"
        )


# ============= LOGGING CONFIGURATION =============


def configure_logging(log_level: str = "INFO", json_logs: bool = True):
    """
    Configure logging with RAG-optimized format.

    Args:
        log_level: Minimum log level (DEBUG, INFO, WARNING, ERROR)
        json_logs: Enable JSON format for log aggregation (Loki, etc.)
    """
    logger.remove()

    if json_logs:
        # JSON format for production (Loki/Grafana compatible)
        logger.add(
            sys.stderr,
            format="{message}",
            level=log_level,
            serialize=True,
            backtrace=False,  # Reduce noise
            diagnose=False,  # Reduce noise
        )

        logger.add(
            "logs/app.log",
            format="{message}",
            level=log_level,
            serialize=True,
            rotation="100 MB",
            retention="30 days",
            compression="zip",
            backtrace=True,
            diagnose=True,
        )
    else:
        # Human-readable format for development
        log_format = (
            "<green>{time:HH:mm:ss.SSS}</green> | "
            "<level>{level: <7}</level> | "
            "<level>{message}</level>"
        )

        logger.add(
            sys.stderr,
            format=log_format,
            level=log_level,
            backtrace=False,
            diagnose=False,
            colorize=True,
        )

        logger.add(
            "logs/app.log",
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <7} | {message}",
            level=log_level,
            rotation="50 MB",
            retention="14 days",
            backtrace=True,
            diagnose=True,
        )


def get_logger():
    """Get base loguru logger."""
    return logger


def get_rag_logger() -> RAGLogger:
    """Get RAG-specific structured logger."""
    return RAGLogger()


# Initialize logging on module import
configure_logging(
    log_level=settings.log_level or "INFO",
    json_logs=False,
)
