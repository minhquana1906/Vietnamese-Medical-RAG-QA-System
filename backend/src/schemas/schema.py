from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class RAGQueryRequest(BaseModel):

    user_identifier: str = Field(..., description="User identifier from authentication")
    thread_id: str = Field(..., description="Thread/conversation ID (UUID)")
    query: str = Field(..., description="User's question")
    metadata: Optional[Dict] = Field(None, description="Additional metadata")


class RAGQueryResponse(BaseModel):

    thread_id: str = Field(..., description="Thread ID")
    response: str = Field(..., description="Assistant's response")
    sources: Optional[List[Dict]] = Field(None, description="Source documents used")
    metadata: Optional[Dict] = Field(None, description="Additional response metadata")


class HealthCheckResponse(BaseModel):
    """Health check response for individual services"""

    status: str = Field(..., description="Health status (ok/error/degraded)")
    service: str = Field(..., description="Service name (api/database/cache)")
    details: Optional[Dict] = Field(None, description="Additional service details")
    message: Optional[str] = Field(None, description="Additional status information")


class SystemHealthResponse(BaseModel):

    status: str = Field(..., description="Overall system status")
    api: HealthCheckResponse = Field(..., description="API health status")
    database: HealthCheckResponse = Field(..., description="Database health status")
    cache: HealthCheckResponse = Field(..., description="Cache health status")


class EmbedRequest(BaseModel):
    """Qwen3-Embedding request with instruction-awareness"""

    texts: List[str]
    normalize: bool = True
    is_query: bool = False  # Set True for queries, False for documents
    instruction: Optional[str] = None  # Optional custom instruction


class EmbedResponse(BaseModel):
    embeddings: List[List[float]]
    model: str


class RerankRequest(BaseModel):
    """Qwen3-Reranker request with task instruction"""

    query: str
    documents: List[str]
    top_n: int = 5
    instruction: Optional[str] = None  # Optional custom instruction


class RerankResponse(BaseModel):
    scores: List[float]
    indices: List[int]
    model: str


class GuardRequest(BaseModel):
    """Qwen3Guard safety check request"""

    text: str
    check_type: str = "input"


class GuardResponse(BaseModel):
    """Qwen3Guard response with 3-tier severity and 9 categories"""

    is_safe: bool
    severity: str  # "Safe" | "Controversial" | "Unsafe"
    categories: List[str]  # List of matched categories (0-8)
    is_refusal: bool  # True if model refuses to answer
    raw_output: str  # Raw model output for debugging/parsing
    model: str
