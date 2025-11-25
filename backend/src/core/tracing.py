"""OpenTelemetry Tracing Utilities for RAG Pipeline"""

from functools import wraps
from typing import Optional, Any, Dict
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from loguru import logger

tracer = trace.get_tracer(__name__)


def trace_rag_stage(stage_name: str, attributes: Optional[Dict[str, Any]] = None):
    """
    Decorator to trace RAG pipeline stages with automatic error handling.
    
    Args:
        stage_name: Name of the RAG stage (e.g., "input_guardrails", "embedding", etc.)
        attributes: Optional dict of attributes to set on span
    
    Usage:
        @trace_rag_stage("query_enhancement")
        def enhance_query(query):
            # Your code here
            return enhanced_query
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            with tracer.start_as_current_span(stage_name) as span:
                # Set custom attributes
                if attributes:
                    for key, value in attributes.items():
                        span.set_attribute(key, value)
                
                try:
                    result = func(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    logger.error(f"Error in {stage_name}: {e}")
                    raise
        
        return wrapper
    return decorator
