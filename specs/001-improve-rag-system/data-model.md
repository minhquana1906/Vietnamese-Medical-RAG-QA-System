# Data Model (Simplified)

**Feature**: RAG System Comprehensive Improvements
**Date**: 2025-11-01
**Status**: Simplified - Using Chainlit Standard Schema

## Overview

This document defines the **simplified** data model. We use Chainlit's standard schema for user/session management and add only simple `documents` and `chunks` tables.

---

## Key Changes from Previous Version

### ✅ What We Keep (Chainlit Standard)
- `users` - Chainlit standard (OAuth only, no passwords)
- `threads` - Chainlit standard (conversation threads)
- `steps` - Chainlit standard (messages)
- `elements` - Chainlit standard (attachments)
- `feedbacks` - Chainlit standard (user ratings)

### ✅ What We Add (Medical Content)
- `documents` - Store medical documents (simple: id, title, content, metadata)
- `chunks` - Store document chunks (simple: id, documentId, chunkIndex, content, metadata)

### ❌ What We Remove (Simplification)
- ~~Custom User table~~ - Use Chainlit's `users`
- ~~Custom ChatSession table~~ - Use Chainlit's `threads`
- ~~Custom Message table~~ - Use Chainlit's `steps`
- ~~FineTunedModel table~~ - Track in HuggingFace Hub/W&B instead
- ~~Password authentication~~ - OAuth only (Google, GitHub)
- ~~JWT tokens~~ - Chainlit handles sessions
- ~~Complex metadata columns~~ - Use JSONB for flexibility

---

## Schema Summary

### Chainlit Tables (Standard - Don't Modify)

See full schema: https://docs.chainlit.io/data-layers/sqlalchemy

```sql
-- Users (OAuth only)
CREATE TABLE users (
    "id" UUID PRIMARY KEY,
    "identifier" TEXT NOT NULL UNIQUE,
    "metadata" JSONB NOT NULL,
    "createdAt" TEXT
);

-- Conversation threads
CREATE TABLE threads (
    "id" UUID PRIMARY KEY,
    "userId" UUID REFERENCES users("id"),
    "name" TEXT,
    "metadata" JSONB,
    ...
);

-- Messages in threads
CREATE TABLE steps (
    "id" UUID PRIMARY KEY,
    "threadId" UUID REFERENCES threads("id"),
    "type" TEXT NOT NULL,
    "input" TEXT,
    "output" TEXT,
    "metadata" JSONB,
    ...
);

-- (elements, feedbacks tables also included)
```

### Custom Tables (Medical Content Only)

```sql
CREATE TABLE documents (
    "id" UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    "title" TEXT NOT NULL,
    "content" TEXT NOT NULL,
    "metadata" JSONB,
    "createdAt" TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE chunks (
    "id" UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    "documentId" UUID REFERENCES documents("id") ON DELETE CASCADE,
    "chunkIndex" INT NOT NULL,
    "content" TEXT NOT NULL,
    "metadata" JSONB,
    "createdAt" TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE("documentId", "chunkIndex")
);
```

---

## External Data Stores

- **Qdrant**: Vector embeddings (chunks.id as point ID)
- **Elasticsearch**: Keyword search index
- **Redis**: Cache for embeddings and search results

---

## Migration

Migration file: `backend/alembic/versions/001_chainlit_schema.py`

Run with:
```bash
cd backend
uv run alembic upgrade head
```

---

## Key Principles

1. **Simplicity**: Only essential attributes, no over-engineering
2. **Leverage Chainlit**: Don't reinvent user/session management
3. **OAuth Only**: No password complexity
4. **Flexible Metadata**: Use JSONB instead of rigid columns
5. **External Stores**: Vector DB and keyword search handled externally

For full Chainlit schema details, see: https://docs.chainlit.io/data-layers/sqlalchemy
