# Schema Simplification Summary

**Date**: 2025-11-01
**Status**: Completed

## Overview

We have simplified the database schema to leverage Chainlit's standard schema and remove unnecessary complexity.

---

## What Changed

### ✅ Database Schema

**Before**: Custom user, chat session, and message tables with password authentication
**After**: Chainlit standard `users`, `threads`, `steps` tables with OAuth only

**Changes**:

1. Removed all custom authentication tables
2. Removed password fields and JWT logic  
3. Use Chainlit's built-in `users`, `threads`, `steps`, `elements`, `feedbacks`
4. Keep simple `documents` and `chunks` tables for medical content (only essential attributes: id, title, content, metadata)

### ✅ Authentication

**Before**: Email/password signup, JWT tokens, password reset
**After**: OAuth only (Google, GitHub) via Chainlit

**Removed**:
- POST /auth/register
- POST /auth/login
- POST /auth/forgot-password
- POST /auth/reset-password
- JWT token generation/validation
- Password hashing logic

### ✅ Models

**File**: `backend/src/models.py`

**Before**: Custom User, ChatSession, Message models
**After**: Chainlit models (User, Thread, Step, Element, Feedback) + simple Document, Chunk

**Changes**:

- Replaced custom models with Chainlit schema
- Removed FineTunedModel (track in HuggingFace/W&B instead)
- Simplified Document (only: id, title, content, metadata, createdAt - removed source, docType)
- Simplified Chunk (only: id, documentId, chunkIndex, content, metadata, createdAt)

### ✅ Migration

**File**: `backend/alembic/versions/001_chainlit_schema.py`

**Actions**:
1. Dropped all old migrations
2. Created new migration with Chainlit schema
3. Added simple documents/chunks tables

---

## Why These Changes?

### Problems with Old Schema

1. **Over-engineering**: Custom auth tables duplicate what Chainlit provides
2. **Complexity**: Password hashing, JWT, session management all custom
3. **Maintenance burden**: More code to maintain and debug
4. **Reinventing the wheel**: Chainlit already solves user/session management

### Benefits of New Schema

1. **Simplicity**: Leverage Chainlit's battle-tested schema
2. **OAuth built-in**: Google/GitHub login out-of-the-box
3. **Session management**: Chainlit handles it internally
4. **Less code**: Remove authentication endpoints and JWT logic
5. **Focus on RAG**: Spend time on medical QA, not auth

---

## What's Next

### Immediate Tasks

1. ✅ Update database schema (DONE)
2. ✅ Update models.py (DONE)
3. ⏳ Remove authentication endpoints from main.py
4. ⏳ Configure Chainlit OAuth (Google, GitHub)
5. ⏳ Update spec.md, plan.md, tasks.md with simplified architecture

### Documentation Updates

- `data-model.md`: ✅ Updated with Chainlit schema
- `spec.md`: ⏳ Remove password auth requirements
- `plan.md`: ⏳ Remove complex auth implementation
- `tasks.md`: ⏳ Remove password/JWT tasks
- `copilot-instructions.md`: ⏳ Update project structure

---

## Migration Guide

### For Development

```bash
# 1. Downgrade to base (if needed)
cd backend
uv run alembic downgrade base

# 2. Delete old migration files
rm alembic/versions/*.py

# 3. Run new migration
uv run alembic upgrade head
```

### For Production

No migration needed - this is a new project with test data only. Just recreate the database with new schema.

---

## References

- Chainlit Data Layer: https://docs.chainlit.io/data-layers/sqlalchemy
- Chainlit OAuth: https://docs.chainlit.io/authentication/oauth
- Migration file: `backend/alembic/versions/001_chainlit_schema.py`
- Updated models: `backend/src/models.py`
- Schema init SQL: `database/init.sql`
