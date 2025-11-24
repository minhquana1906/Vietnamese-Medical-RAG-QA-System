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


class CacheStatisticsResponse(BaseModel):
    """Cache statistics and performance metrics"""

    total_keys: int = Field(..., description="Total number of keys in cache")
    embedding_cache_keys: int = Field(
        ..., description="Number of embedding cache entries"
    )
    search_cache_keys: int = Field(..., description="Number of search cache entries")
    conversation_keys: int = Field(
        ..., description="Number of conversation cache entries"
    )
    keyspace_hits: int = Field(..., description="Total cache hits")
    keyspace_misses: int = Field(..., description="Total cache misses")
    hit_rate: float = Field(..., description="Cache hit rate (0.0-1.0)")
    memory_used: Optional[str] = Field(None, description="Memory usage (if available)")


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
    check_type: str = "input"  # "input" | "output"
    query: Optional[str] = (
        None  # Required for output moderation (user's original query)
    )


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

    dataset_name: str = Field(
        "quannguyen204/vietnamese_medical_corpus_dataset",
        description="HuggingFace dataset identifier",
    )
    dataset_config: Optional[str] = Field(
        "default", description="Dataset configuration name"
    )
    split: str = Field("train", description="Dataset split to load")
    doc_type: Optional[str] = Field(
        "clinical_guideline", description="Document type for all documents in dataset"
    )
    max_documents: Optional[int] = Field(
        None, description="Limit number of documents to ingest (for testing)"
    )
    batch_size: int = Field(
        512,
        description="Number of documents to process in each batch (affects DB commit frequency and memory usage)",
        ge=1,
        le=1000,
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


# Audio/Speech Schemas


class SttRequest(BaseModel):
    """Speech-to-Text request (via file upload)"""

    # File will be uploaded via multipart/form-data
    language: Optional[str] = Field(
        "vi", description="Language code (default: Vietnamese)"
    )


class SttResponse(BaseModel):
    """Speech-to-Text response"""

    text: str = Field(..., description="Transcribed text")
    language: str = Field(..., description="Detected/specified language")
    duration: float = Field(..., description="Audio duration in seconds")
    cached: bool = Field(False, description="Whether result was from cache")


class TtsRequest(BaseModel):
    """Text-to-Speech request"""

    text: str = Field(
        ..., description="Text to synthesize", min_length=1, max_length=5000
    )
    voice_id: Optional[str] = Field(
        None, description="Voice identifier (uses default from settings if None)"
    )
    model_id: Optional[str] = Field(
        None, description="TTS model identifier (uses default from settings if None)"
    )
    stability: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Voice stability (uses default from settings if None)",
    )
    similarity_boost: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Clarity/similarity boost (uses default from settings if None)",
    )
    speed: float = Field(1.0, ge=0.5, le=2.0, description="Speech speed multiplier")


class TtsResponse(BaseModel):
    """Text-to-Speech response (audio returned as file)"""

    message: str = Field(..., description="Status message")
    audio_size: int = Field(..., description="Audio file size in bytes")
    cached: bool = Field(False, description="Whether result was from cache")


class AudioRagRequest(BaseModel):
    """Combined Speech-to-Speech RAG request (via file upload)"""

    # Audio file uploaded via multipart/form-data
    user_identifier: str = Field(..., description="User identifier")
    thread_id: str = Field(..., description="Thread/conversation ID")
    language: Optional[str] = Field("vi", description="STT language code")
    voice_id: Optional[str] = Field(None, description="TTS voice identifier")


class AudioRagResponse(BaseModel):
    """Combined Speech-to-Speech RAG response"""

    thread_id: str = Field(..., description="Thread ID")
    transcript: str = Field(..., description="Transcribed user query")
    response: str = Field(..., description="Assistant's text response")
    audio_url: str = Field(..., description="URL to download generated audio file")
    sources: Optional[List[Dict]] = Field(None, description="Source documents")
    metadata: Optional[Dict] = Field(None, description="Processing metadata")
