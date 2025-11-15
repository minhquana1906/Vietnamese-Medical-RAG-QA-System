# Data Model

**Feature**: RAG System Comprehensive Improvements
**Phase**: 1 - Design
**Date**: 2025-10-31

## Overview

This document defines the data entities, relationships, and schemas for the upgraded RAG system. The model supports Chainlit UI with authentication, enhanced document management, and comprehensive monitoring.

---

## Entity Relationship Diagram

```
┌─────────────┐       ┌──────────────┐       ┌─────────────┐
│    User     │1    * │ ChatSession  │1    * │   Message   │
│             │───────│  (Thread)    │───────│             │
│             │       │              │       │             │
└─────────────┘       └──────────────┘       └─────────────┘

┌─────────────┐       ┌──────────────┐       ┌─────────────┐
│  Document   │1    * │    Chunk     │*    1 │  Embedding  │
│             │───────│              │───────│   (Vector)  │
│             │       │              │       │             │
└─────────────┘       └──────────────┘       └─────────────┘
       │
       │*
       │
┌─────────────┐
│  Metadata   │
│             │
└─────────────┘

┌─────────────┐       ┌──────────────┐
│ FineTunedModel│     │  CacheEntry  │
│             │       │              │
└─────────────┘       └──────────────┘

┌─────────────┐       ┌──────────────┐
│   Metric    │       │   LogEntry   │
│             │       │              │
└─────────────┘       └──────────────┘
```

---

## Core Entities

### 1. User

Represents an authenticated user of the medical RAG system.

**Attributes**:
- `id` (UUID, PK): Unique user identifier
- `email` (String, unique): User's email address
- `password_hash` (String, nullable): Hashed password (null for OAuth users)
- `oauth_provider` (String, nullable): OAuth provider name (google, github, etc.)
- `oauth_id` (String, nullable): OAuth user ID from provider
- `display_name` (String): User's display name
- `created_at` (DateTime): Account creation timestamp
- `last_login` (DateTime, nullable): Last login timestamp
- `is_active` (Boolean): Account active status
- `metadata` (JSONB): Additional user preferences/settings

**Relationships**:
- `chat_sessions`: One-to-many with ChatSession

**Validation Rules**:
- Email must be valid format
- Either password_hash OR (oauth_provider + oauth_id) must be present
- Email must be unique across all users

**State Transitions**:
- `pending` → `active` (after email verification)
- `active` → `suspended` (admin action)
- `suspended` → `active` (admin action)

---

### 2. ChatSession (Thread)

Represents a conversation thread between a user and the RAG system.

**Attributes**:
- `id` (UUID, PK): Unique session identifier
- `user_id` (UUID, FK → User): Owner of the session
- `name` (String, nullable): Optional session name/title
- `created_at` (DateTime): Session creation timestamp
- `updated_at` (DateTime): Last message timestamp
- `metadata` (JSONB): Session-specific settings (e.g., model preferences, language)
- `is_active` (Boolean): Whether session is currently active

**Relationships**:
- `user`: Many-to-one with User
- `messages`: One-to-many with Message

**Validation Rules**:
- User ID must reference valid user
- At least one message required for session to be considered "active"

**Indexes**:
- `idx_chat_session_user_id` on `user_id`
- `idx_chat_session_updated_at` on `updated_at` (for recent sessions query)

---

### 3. Message (Step)

Represents a single message in a conversation (user query or assistant response).

**Attributes**:
- `id` (UUID, PK): Unique message identifier
- `chat_session_id` (UUID, FK → ChatSession): Parent session
- `role` (Enum: 'user', 'assistant', 'system'): Message sender role
- `content` (Text): Message text content
- `created_at` (DateTime): Message timestamp
- `metadata` (JSONB): Additional context (retrieved documents, model used, latency)
- `parent_message_id` (UUID, FK → Message, nullable): For threaded conversations

**Relationships**:
- `chat_session`: Many-to-one with ChatSession
- `parent_message`: Self-referential for message threads

**Validation Rules**:
- Content cannot be empty
- Role must be one of: user, assistant, system
- created_at must be <= parent message created_at (if parent exists)

**Indexes**:
- `idx_message_session_id` on `chat_session_id`
- `idx_message_created_at` on `created_at`

---

### 4. Document

Represents a source medical document that has been indexed.

**Attributes**:
- `id` (UUID, PK): Unique document identifier
- `title` (String): Document title
- `content` (Text): Full document content
- `source` (String): Source identifier (dataset name, URL, etc.)
- `doc_type` (Enum): Document category (clinical_guideline, drug_info, medical_qa, research_paper)
- `language` (String): Document language (vi, en)
- `created_at` (DateTime): Document ingestion timestamp
- `updated_at` (DateTime): Last modification timestamp
- `metadata` (JSONB): Additional fields (author, publication_date, specialty, etc.)
- `is_indexed` (Boolean): Whether document has been chunked and indexed

**Relationships**:
- `chunks`: One-to-many with Chunk

**Validation Rules**:
- Title and content cannot be empty
- Source must be specified
- Language must be ISO 639-1 code

**Indexes**:
- `idx_document_source` on `source`
- `idx_document_type` on `doc_type`
- `idx_document_is_indexed` on `is_indexed`

---

### 5. Chunk

Represents a segmented portion of a document that has been indexed for retrieval.

**Attributes**:
- `id` (UUID, PK): Unique chunk identifier
- `document_id` (UUID, FK → Document): Parent document
- `chunk_index` (Integer): Position in document (0-based)
- `content` (Text): Chunk text content
- `token_count` (Integer): Number of tokens in chunk
- `overlap_start` (Integer): Characters overlapping with previous chunk
- `overlap_end` (Integer): Characters overlapping with next chunk
- `created_at` (DateTime): Chunk creation timestamp
- `metadata` (JSONB): Chunk-specific metadata (section_title, page_number, etc.)

**Relationships**:
- `document`: Many-to-one with Document
- `embedding`: One-to-one with vector in Qdrant (logical, not FK)

**Validation Rules**:
- chunk_index must be >= 0
- content cannot be empty
- token_count must be > 0 and <= max_chunk_size (512)

**Indexes**:
- `idx_chunk_document_id` on `document_id`
- `idx_chunk_document_index` on `(document_id, chunk_index)` (unique constraint)

**Note**: Embedding vectors are stored in Qdrant, with chunk.id as the point ID for cross-referencing.

---

### 6. FineTunedModel

Tracks fine-tuned model versions and their performance metrics.

**Attributes**:
- `id` (UUID, PK): Unique model identifier
- `model_name` (String): Base model name (e.g., "Qwen3-4B-Instruct-2507")
- `model_type` (Enum: 'generation', 'embedding', 'reranking', 'guardrails'): Model purpose
- `version` (String): Model version/tag
- `huggingface_repo` (String): HuggingFace Hub repository ID
- `wandb_run_id` (String, nullable): W&B experiment run ID
- `training_dataset` (String): Dataset used for fine-tuning
- `baseline_metrics` (JSONB): Performance metrics before fine-tuning
- `finetuned_metrics` (JSONB): Performance metrics after fine-tuning
- `improvement_pct` (Float): Percentage improvement over baseline
- `is_deployed` (Boolean): Whether model is currently serving
- `created_at` (DateTime): Model creation timestamp
- `deployed_at` (DateTime, nullable): Deployment timestamp

**Validation Rules**:
- model_name and version combination must be unique
- improvement_pct must be calculated from baseline and finetuned metrics
- is_deployed can only be true if improvement_pct >= 2.0 (2% threshold)

**Indexes**:
- `idx_model_type` on `model_type`
- `idx_model_deployed` on `is_deployed`

---

### 7. CacheEntry

Represents cached query embeddings or search results.

**Attributes**:
- `cache_key` (String, PK): MD5 hash of cached item (e.g., query text)
- `cache_type` (Enum: 'embedding', 'search_vector', 'search_keyword', 'search_hybrid'): Type of cached data
- `value` (JSONB or Binary): Cached data
- `created_at` (DateTime): Cache creation timestamp
- `accessed_at` (DateTime): Last access timestamp
- `access_count` (Integer): Number of cache hits
- `ttl` (Integer): Time-to-live in seconds
- `expires_at` (DateTime): Expiration timestamp (created_at + ttl)

**Validation Rules**:
- cache_key must be 32-character MD5 hash
- ttl must be > 0
- expires_at = created_at + ttl

**Indexes**:
- `idx_cache_expires_at` on `expires_at` (for cleanup)
- `idx_cache_type` on `cache_type`

**Note**: In practice, cache is stored in Redis (not PostgreSQL) for performance. This entity documents the logical model.

---

### 8. Metric

Represents collected performance metrics from the RAG pipeline.

**Attributes**:
- `id` (UUID, PK): Unique metric identifier
- `metric_name` (String): Metric name (e.g., "rag_request_duration_seconds")
- `metric_type` (Enum: 'counter', 'histogram', 'gauge'): Prometheus metric type
- `value` (Float): Metric value
- `labels` (JSONB): Metric labels (e.g., {"model": "qwen3", "endpoint": "/chat"})
- `timestamp` (DateTime): Measurement timestamp

**Validation Rules**:
- metric_name must follow Prometheus naming conventions (lowercase, underscores)
- value must be non-negative for counters and histograms

**Indexes**:
- `idx_metric_name_timestamp` on `(metric_name, timestamp)`
- `idx_metric_timestamp` on `timestamp` (for time-series queries)

**Note**: Metrics are primarily stored in Prometheus. This entity documents the logical model for PostgreSQL backup.

---

### 9. LogEntry

Represents structured log entries from the application.

**Attributes**:
- `id` (UUID, PK): Unique log entry identifier
- `level` (Enum: 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'): Log level
- `message` (Text): Log message
- `logger_name` (String): Logger source (e.g., "backend.services.brain")
- `timestamp` (DateTime): Log timestamp
- `user_id` (UUID, nullable): Associated user (if applicable)
- `chat_session_id` (UUID, nullable): Associated chat session (if applicable)
- `trace_id` (String, nullable): Distributed trace ID
- `span_id` (String, nullable): Span ID within trace
- `metadata` (JSONB): Additional context fields

**Validation Rules**:
- level must be valid log level
- message cannot be empty

**Indexes**:
- `idx_log_level_timestamp` on `(level, timestamp)`
- `idx_log_trace_id` on `trace_id`
- `idx_log_timestamp` on `timestamp`

**Note**: Logs are primarily stored in Loki. This entity documents the logical model for PostgreSQL backup.

---

## External Data Stores

### Qdrant (Vector Database)

**Collection**: `medical_documents`

**Point Structure**:
```json
{
  "id": "<chunk.id UUID>",
  "vector": [0.123, -0.456, ...],  // 1024 dimensions for Qwen3-Embedding-0.6B
  "payload": {
    "document_id": "<document.id UUID>",
    "chunk_index": 0,
    "content": "Chunk text content...",
    "title": "Document title",
    "doc_type": "clinical_guideline",
    "source": "combined_medical_dataset",
    "metadata": {...}
  }
}
```

**Indexes**:
- HNSW index on vectors for efficient similarity search
- Payload indexes on: `document_id`, `doc_type`, `source`

---

### Elasticsearch (Keyword Search)

**Index**: `medical_documents`

**Document Structure**:
```json
{
  "id": "<chunk.id UUID>",
  "document_id": "<document.id UUID>",
  "chunk_index": 0,
  "content": "Chunk text content...",
  "title": "Document title",
  "doc_type": "clinical_guideline",
  "source": "combined_medical_dataset",
  "metadata": {...}
}
```

**Mappings**:
- `content`: text field with Vietnamese analyzer
- `title`: text field with Vietnamese analyzer
- `doc_type`: keyword field
- `source`: keyword field

---

### Redis (Cache)

**Key Patterns**:

1. **Query Embeddings**:
   - Key: `emb:<md5(query)>`
   - Value: JSON array of floats
   - TTL: 3600 seconds (1 hour)

2. **Search Results**:
   - Key: `search:<search_type>:<md5(query)>`
   - Value: JSON array of document IDs and scores
   - TTL: 600 seconds (10 minutes)

3. **User Sessions** (Celery conversation tracking):
   - Key: `<bot_id>.<user_id>`
   - Value: conversation_id
   - TTL: 360 seconds

---

## Database Schema (PostgreSQL)

### users
```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255),
    oauth_provider VARCHAR(50),
    oauth_id VARCHAR(255),
    display_name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_login TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT TRUE,
    metadata JSONB DEFAULT '{}'::jsonb,
    CONSTRAINT email_format CHECK (email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}$'),
    CONSTRAINT auth_method CHECK (
        (password_hash IS NOT NULL) OR
        (oauth_provider IS NOT NULL AND oauth_id IS NOT NULL)
    )
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_oauth ON users(oauth_provider, oauth_id) WHERE oauth_provider IS NOT NULL;
```

### chat_sessions
```sql
CREATE TABLE chat_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE INDEX idx_chat_sessions_user_id ON chat_sessions(user_id);
CREATE INDEX idx_chat_sessions_updated_at ON chat_sessions(updated_at DESC);
```

### messages
```sql
CREATE TYPE message_role AS ENUM ('user', 'assistant', 'system');

CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role message_role NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb,
    parent_message_id UUID REFERENCES messages(id) ON DELETE SET NULL
);

CREATE INDEX idx_messages_session_id ON messages(chat_session_id);
CREATE INDEX idx_messages_created_at ON messages(created_at);
```

### documents
```sql
CREATE TYPE doc_type AS ENUM ('clinical_guideline', 'drug_info', 'medical_qa', 'research_paper', 'other');

CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(500) NOT NULL,
    content TEXT NOT NULL,
    source VARCHAR(255) NOT NULL,
    doc_type doc_type NOT NULL,
    language VARCHAR(2) DEFAULT 'vi',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb,
    is_indexed BOOLEAN DEFAULT FALSE
);

CREATE INDEX idx_documents_source ON documents(source);
CREATE INDEX idx_documents_type ON documents(doc_type);
CREATE INDEX idx_documents_indexed ON documents(is_indexed);
```

### chunks
```sql
CREATE TABLE chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    token_count INTEGER NOT NULL,
    overlap_start INTEGER DEFAULT 0,
    overlap_end INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb,
    UNIQUE(document_id, chunk_index),
    CONSTRAINT valid_chunk_index CHECK (chunk_index >= 0),
    CONSTRAINT valid_token_count CHECK (token_count > 0 AND token_count <= 512)
);

CREATE INDEX idx_chunks_document_id ON chunks(document_id);
CREATE INDEX idx_chunks_document_index ON chunks(document_id, chunk_index);
```

### fine_tuned_models
```sql
CREATE TYPE model_type AS ENUM ('generation', 'embedding', 'reranking', 'guardrails');

CREATE TABLE fine_tuned_models (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_name VARCHAR(255) NOT NULL,
    model_type model_type NOT NULL,
    version VARCHAR(100) NOT NULL,
    huggingface_repo VARCHAR(255) NOT NULL,
    wandb_run_id VARCHAR(255),
    training_dataset VARCHAR(255) NOT NULL,
    baseline_metrics JSONB NOT NULL,
    finetuned_metrics JSONB NOT NULL,
    improvement_pct FLOAT NOT NULL,
    is_deployed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    deployed_at TIMESTAMP WITH TIME ZONE,
    UNIQUE(model_name, version),
    CONSTRAINT valid_improvement CHECK (is_deployed = FALSE OR improvement_pct >= 2.0)
);

CREATE INDEX idx_fine_tuned_models_type ON fine_tuned_models(model_type);
CREATE INDEX idx_fine_tuned_models_deployed ON fine_tuned_models(is_deployed);
```

---

## Data Flow Diagrams

### 1. User Registration & Authentication Flow

```
[User Input] → [Chainlit Auth Handler]
                    ↓
    ┌───────────────┴───────────────┐
    │ Email/Password    │   OAuth   │
    ↓                   ↓           ↓
[Hash Password]   [Verify Token]  [Get Profile]
    ↓                   ↓           ↓
    └───────────────┬───────────────┘
                    ↓
            [Create User Record]
                    ↓
            [Create Session Token]
                    ↓
            [Return to Chainlit]
```

### 2. RAG Query Processing Flow

```
[User Query] → [Chainlit Message Handler]
                        ↓
                [Create Message Record]
                        ↓
                [Celery Task: message_handler_task]
                        ↓
            ┌───────────┴────────────┐
            │   Check Cache          │
            │   (Redis: emb:*)       │
            └───────────┬────────────┘
                        ↓
            ┌───────────┴────────────┐
            │ Cache Hit?             │
            ├─────────────┬──────────┤
            │ Yes         │ No       │
            ↓             ↓          │
    [Use Cached    [Generate        │
     Embedding]     Embedding]      │
            │             ↓          │
            │      [Cache Result]   │
            └───────────┬────────────┘
                        ↓
            ┌───────────┴────────────┐
            │  Hybrid Search         │
            │  - Qdrant (vector)     │
            │  - Elasticsearch (BM25)│
            │  - RRF Fusion          │
            └───────────┬────────────┘
                        ↓
            [Rerank with Qwen3-Reranker]
                        ↓
            [Generate Response with Qwen3-Gen]
                        ↓
            [Guardrails Check with Qwen3-Guard]
                        ↓
            [Save Assistant Message]
                        ↓
            [Return Response to Chainlit]
```

### 3. Document Indexing Flow

```
[HF Dataset Load] → [Celery Task: chunk_and_index_document]
                            ↓
                    [Create Document Record]
                            ↓
                    [Semantic Chunking]
                            ↓
            ┌───────────────┴──────────────┐
            │ For each chunk:              │
            │ 1. Create Chunk Record       │
            │ 2. Generate Embedding        │
            │ 3. Insert to Qdrant          │
            │ 4. Index to Elasticsearch    │
            └───────────────┬──────────────┘
                            ↓
                    [Update Document.is_indexed]
                            ↓
                    [Log Metrics to Prometheus]
```

---

## Migration Strategy

### Alembic Migration: Chainlit Schema

**Migration File**: `alembic/versions/XXXX_chainlit_schema.py`

```python
"""Migrate to Chainlit-compatible schema

Revision ID: XXXX
Revises: 9290fad6ca4e
Create Date: 2025-10-31

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    # Create users table
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('email', sa.String(255), unique=True, nullable=False),
        sa.Column('password_hash', sa.String(255), nullable=True),
        sa.Column('oauth_provider', sa.String(50), nullable=True),
        sa.Column('oauth_id', sa.String(255), nullable=True),
        sa.Column('display_name', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('last_login', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('metadata', postgresql.JSONB, server_default=sa.text("'{}'::jsonb"))
    )

    # Create chat_sessions table (threads)
    op.create_table(
        'chat_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('metadata', postgresql.JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column('is_active', sa.Boolean, default=True)
    )

    # Create messages table (steps)
    op.create_table(
        'messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('chat_session_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('chat_sessions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role', sa.Enum('user', 'assistant', 'system', name='message_role'), nullable=False),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('metadata', postgresql.JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column('parent_message_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('messages.id', ondelete='SET NULL'), nullable=True)
    )

    # Add fine_tuned_models table
    op.create_table(
        'fine_tuned_models',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('model_name', sa.String(255), nullable=False),
        sa.Column('model_type', sa.Enum('generation', 'embedding', 'reranking', 'guardrails', name='model_type'), nullable=False),
        sa.Column('version', sa.String(100), nullable=False),
        sa.Column('huggingface_repo', sa.String(255), nullable=False),
        sa.Column('wandb_run_id', sa.String(255), nullable=True),
        sa.Column('training_dataset', sa.String(255), nullable=False),
        sa.Column('baseline_metrics', postgresql.JSONB, nullable=False),
        sa.Column('finetuned_metrics', postgresql.JSONB, nullable=False),
        sa.Column('improvement_pct', sa.Float, nullable=False),
        sa.Column('is_deployed', sa.Boolean, default=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('deployed_at', sa.DateTime(timezone=True), nullable=True)
    )

    # Create indexes
    op.create_index('idx_users_email', 'users', ['email'])
    op.create_index('idx_chat_sessions_user_id', 'chat_sessions', ['user_id'])
    op.create_index('idx_chat_sessions_updated_at', 'chat_sessions', ['updated_at'], postgresql_ops={'updated_at': 'DESC'})
    op.create_index('idx_messages_session_id', 'messages', ['chat_session_id'])
    op.create_index('idx_messages_created_at', 'messages', ['created_at'])
    op.create_index('idx_fine_tuned_models_type', 'fine_tuned_models', ['model_type'])
    op.create_index('idx_fine_tuned_models_deployed', 'fine_tuned_models', ['is_deployed'])

def downgrade():
    op.drop_table('messages')
    op.drop_table('chat_sessions')
    op.drop_table('users')
    op.drop_table('fine_tuned_models')
    op.execute('DROP TYPE message_role')
    op.execute('DROP TYPE model_type')
```

### Data Migration Script

For migrating existing conversations from old schema to new Chainlit schema:

**Script**: `backend/scripts/migrate_conversations.py`

```python
"""
Migrate existing conversation data to Chainlit schema.
Assumes old schema has Conversation and Message tables.
"""
import uuid
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from backend.src.database import get_database_settings

# Old models (pseudo-code, adapt to actual schema)
# class OldConversation: id, bot_id, user_identifier, messages
# class OldMessage: id, conversation_id, role, content, timestamp

def migrate_conversations():
    settings = get_database_settings()
    engine = create_engine(settings.database_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    # 1. Create default user for legacy conversations
    default_user_id = uuid.uuid4()
    session.execute(
        "INSERT INTO users (id, email, display_name, password_hash) VALUES (%s, %s, %s, %s)",
        (default_user_id, "legacy@system.local", "Legacy User", "")
    )

    # 2. Migrate conversations to chat_sessions
    old_conversations = session.execute("SELECT * FROM old_conversations").fetchall()
    for old_conv in old_conversations:
        new_session_id = uuid.uuid4()
        session.execute(
            """INSERT INTO chat_sessions (id, user_id, name, created_at, metadata)
               VALUES (%s, %s, %s, %s, %s)""",
            (new_session_id, default_user_id, f"Legacy Chat {old_conv.id}",
             old_conv.created_at, {"legacy_id": old_conv.id})
        )

        # 3. Migrate messages
        old_messages = session.execute(
            "SELECT * FROM old_messages WHERE conversation_id = %s ORDER BY timestamp",
            (old_conv.id,)
        ).fetchall()

        for old_msg in old_messages:
            session.execute(
                """INSERT INTO messages (id, chat_session_id, role, content, created_at, metadata)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (uuid.uuid4(), new_session_id, old_msg.role, old_msg.content,
                 old_msg.timestamp, {"legacy_id": old_msg.id})
            )

    session.commit()
    print(f"Migrated {len(old_conversations)} conversations")

if __name__ == "__main__":
    migrate_conversations()
```

---

## Summary

This data model provides:

1. **User Management**: Full authentication with OAuth support (Chainlit-compatible)
2. **Conversation Tracking**: Persistent chat sessions with message history
3. **Document Management**: Hierarchical document → chunk → embedding structure
4. **Model Versioning**: Track fine-tuned models with performance metrics
5. **Caching**: Logical model for Redis cache entries
6. **Observability**: Metrics and logs (primarily in Prometheus/Loki, backed up in PostgreSQL)

**Key Design Decisions**:
- PostgreSQL for relational data (users, sessions, messages, documents)
- Qdrant for vector embeddings (efficient similarity search)
- Elasticsearch for keyword search (BM25 scoring)
- Redis for caching (low-latency access)
- Prometheus/Loki/Tempo for observability (time-series data)
- HuggingFace Hub for model artifacts (external registry)
- W&B for experiment tracking (external platform)

**Next Steps**: Define API contracts in `contracts/` directory.
