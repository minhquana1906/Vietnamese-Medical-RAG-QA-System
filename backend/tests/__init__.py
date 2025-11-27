"""Backend test suite for Vietnamese Medical RAG QA System.

This package contains pytest tests covering:
- API health/readiness checks
- RAG endpoint validation and functionality
- Retrieval layer fallback behavior
- LLM output evaluation
- Safety guardrails
- Logging and monitoring

All tests are designed to run without external service dependencies by using mocked
components via conftest.py fixtures.
"""
