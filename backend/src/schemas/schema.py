from typing import Dict, List, Optional
from uuid import UUID

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


# Document and Indexing Schemas


class IngestDatasetRequest(BaseModel):
    """Request to ingest a HuggingFace dataset"""

    dataset_name: str = Field(..., description="HuggingFace dataset identifier")
    dataset_config: Optional[str] = Field(None, description="Dataset configuration name")
    split: str = Field("train", description="Dataset split to load")
    doc_type: Optional[str] = Field(
        None, description="Document type for all documents in dataset"
    )
    max_documents: Optional[int] = Field(
        None, description="Limit number of documents to ingest (for testing)"
    )


class IngestDatasetResponse(BaseModel):
    """Response with job ID for async indexing"""

    job_id: str = Field(..., description="Celery task ID for tracking progress")
    status: str = Field(..., description="Initial status (pending)")
    message: str = Field(..., description="Status message")


class IndexingJobStatusResponse(BaseModel):
    """Status of an indexing job"""

    job_id: str
    status: str  # pending, running, completed, failed
    progress: Optional[Dict] = None
    result: Optional[Dict] = None
    error: Optional[str] = None


class DocumentCreate(BaseModel):
    """Request to create a document"""

    title: str = Field(..., max_length=500)
    content: str = Field(..., min_length=1)
    source: str
    doc_type: Optional[str] = None
    language: str = Field("vi", min_length=2, max_length=2)
    metadata: Optional[Dict] = None


class DocumentResponse(BaseModel):
    """Document response with metadata"""

    id: UUID
    title: str
    content: str
    source: Optional[str] = None
    doc_type: Optional[str] = None
    language: Optional[str] = None
    created_at: str
    is_indexed: bool = False
    metadata: Optional[Dict] = None

    class Config:
        from_attributes = True


class ChunkResponse(BaseModel):
    """Chunk response with metadata"""

    id: UUID
    document_id: UUID
    chunk_index: int
    content: str
    token_count: Optional[int] = None
    overlap_start: Optional[int] = None
    overlap_end: Optional[int] = None
    created_at: str
    metadata: Optional[Dict] = None

    class Config:
        from_attributes = True


class DocumentDetailResponse(DocumentResponse):
    """Document with chunks"""

    chunks: List[ChunkResponse] = []


class DocumentListResponse(BaseModel):
    """Paginated document list"""

    documents: List[DocumentResponse]
    total: int
    limit: int
    offset: int


class ReindexDocumentResponse(BaseModel):
    """Response for reindexing a document"""

    job_id: str
    status: str
    message: str
