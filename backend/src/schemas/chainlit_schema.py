from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

# ============= ENUMS =============


class MessageRole(str, Enum):
    user = "user"
    assistant = "assistant"
    system = "system"


class ModelType(str, Enum):
    generation = "generation"
    embedding = "embedding"
    reranking = "reranking"
    guardrails = "guardrails"


class DocType(str, Enum):
    clinical_guideline = "clinical_guideline"
    drug_info = "drug_info"
    medical_qa = "medical_qa"
    research_paper = "research_paper"
    other = "other"


# ============= USER SCHEMAS =============


class UserBase(BaseModel):
    email: EmailStr
    display_name: str


class UserCreate(UserBase):
    password: str = Field(
        ..., min_length=8, description="Password must be at least 8 characters"
    )

    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        if not any(char.isdigit() for char in v):
            raise ValueError("Password must contain at least one digit")
        if not any(char.isupper() for char in v):
            raise ValueError("Password must contain at least one uppercase letter")
        return v


class UserOAuthCreate(UserBase):
    oauth_provider: str
    oauth_id: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(UserBase):
    id: UUID
    oauth_provider: Optional[str] = None
    created_at: datetime
    last_login: Optional[datetime] = None
    is_active: bool
    metadata: Dict = Field(default_factory=dict)

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    metadata: Optional[Dict] = None


# ============= AUTHENTICATION SCHEMAS =============


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class TokenData(BaseModel):
    user_id: UUID
    email: str


# ============= CHAT SESSION SCHEMAS =============


class ChatSessionBase(BaseModel):
    name: Optional[str] = None


class ChatSessionCreate(ChatSessionBase):
    pass


class ChatSessionUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None
    metadata: Optional[Dict] = None


class ChatSessionResponse(ChatSessionBase):
    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime
    metadata: Dict = Field(default_factory=dict)
    is_active: bool
    message_count: Optional[int] = None

    class Config:
        from_attributes = True


class ChatSessionListResponse(BaseModel):
    """Schema for list of chat sessions."""

    sessions: List[ChatSessionResponse]
    total: int


# ============= MESSAGE SCHEMAS =============


class MessageBase(BaseModel):
    content: str = Field(
        ..., min_length=1, description="Message content cannot be empty"
    )


class MessageCreate(MessageBase):
    role: MessageRole = MessageRole.user
    parent_message_id: Optional[UUID] = None


class MessageResponse(MessageBase):
    id: UUID
    chat_session_id: UUID
    role: MessageRole
    created_at: datetime
    metadata: Dict = Field(default_factory=dict)
    parent_message_id: Optional[UUID] = None

    class Config:
        from_attributes = True


class MessageListResponse(BaseModel):
    messages: List[MessageResponse]
    total: int


class ChatMessageRequest(BaseModel):
    content: str = Field(
        ..., min_length=1, description="Message content cannot be empty"
    )
    stream: bool = Field(default=False, description="Enable streaming response")


class ChatMessageResponse(BaseModel):
    user_message: MessageResponse
    assistant_message: MessageResponse
    retrieved_documents: Optional[List[Dict]] = None
    latency_ms: Optional[float] = None


# ============= DOCUMENT SCHEMAS =============


class DocumentBase(BaseModel):
    title: str
    content: str
    source: Optional[str] = None
    doc_type: Optional[DocType] = None
    language: str = "vi"


class DocumentCreate(DocumentBase):
    metadata: Optional[Dict] = None


class DocumentUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    source: Optional[str] = None
    doc_type: Optional[DocType] = None
    metadata: Optional[Dict] = None


class DocumentResponse(DocumentBase):
    id: int
    is_indexed: bool
    metadata: Dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    chunk_count: Optional[int] = None

    class Config:
        from_attributes = True


class DocumentListResponse(BaseModel):
    documents: List[DocumentResponse]
    total: int


# ============= CHUNK SCHEMAS =============


class ChunkBase(BaseModel):
    document_id: int
    chunk_index: int
    content: str
    token_count: int


class ChunkCreate(ChunkBase):
    overlap_start: int = 0
    overlap_end: int = 0
    metadata: Optional[Dict] = None


class ChunkResponse(ChunkBase):
    id: UUID
    overlap_start: int
    overlap_end: int
    created_at: datetime
    metadata: Dict = Field(default_factory=dict)

    class Config:
        from_attributes = True


# ============= FINE-TUNED MODEL SCHEMAS =============


class FineTunedModelBase(BaseModel):
    model_name: str
    model_type: ModelType
    version: str
    huggingface_repo: str
    training_dataset: str


class FineTunedModelCreate(FineTunedModelBase):
    wandb_run_id: Optional[str] = None
    baseline_metrics: Dict
    finetuned_metrics: Dict
    improvement_pct: float = Field(
        ..., ge=0.0, description="Percentage improvement over baseline"
    )

    @field_validator("improvement_pct")
    @classmethod
    def validate_improvement(cls, v, info):
        """Validate improvement percentage."""
        if v < 0:
            raise ValueError("Improvement percentage cannot be negative")
        return v


class FineTunedModelResponse(FineTunedModelBase):
    id: UUID
    wandb_run_id: Optional[str] = None
    baseline_metrics: Dict
    finetuned_metrics: Dict
    improvement_pct: float
    is_deployed: bool
    created_at: datetime
    deployed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class FineTunedModelListResponse(BaseModel):
    models: List[FineTunedModelResponse]
    total: int


class ModelDeploymentRequest(BaseModel):
    force: bool = Field(
        default=False, description="Force deployment even if improvement < 2%"
    )


# ============= INDEXING SCHEMAS =============


class IngestDatasetRequest(BaseModel):
    dataset_name: str = Field(..., description="HuggingFace dataset name")
    doc_type: DocType
    max_documents: Optional[int] = Field(
        None, description="Maximum number of documents to ingest (null for all)"
    )
    chunk_size: int = Field(
        512, ge=128, le=1024, description="Maximum tokens per chunk"
    )
    chunk_overlap: int = Field(
        50, ge=0, le=200, description="Overlap tokens between chunks"
    )


class IndexingJobResponse(BaseModel):
    job_id: UUID
    status: str  # 'pending', 'running', 'completed', 'failed'
    progress: Optional[int] = Field(
        None, ge=0, le=100, description="Progress percentage"
    )
    result: Optional[Dict] = None
    error: Optional[str] = None


# ============= HEALTH CHECK SCHEMAS =============


class HealthCheckResponse(BaseModel):
    status: str  # 'ok', 'degraded', 'error'
    service: str
    details: Optional[Dict] = None


class SystemHealthResponse(BaseModel):
    status: str  # 'healthy', 'degraded', 'unhealthy'
    api: HealthCheckResponse
    database: HealthCheckResponse
    cache: HealthCheckResponse
    models: Optional[HealthCheckResponse] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
