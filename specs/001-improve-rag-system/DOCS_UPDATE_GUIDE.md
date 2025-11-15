# Documentation Updates Required

**Date**: 2025-11-01
**Status**: In Progress

## Summary

Following the schema simplification, these documents need to be updated to reflect the new architecture:

---

## 1. spec.md Updates

### Remove These Requirements

#### Authentication (FR-002, FR-003, FR-004)
- ~~FR-002: Email/password authentication~~
- ~~FR-003: Password reset functionality~~
- ~~FR-004: JWT token management~~

**Replace with**:
- FR-002: OAuth authentication (Google, GitHub) via Chainlit
- FR-003: Session management handled by Chainlit
- FR-004: User profile retrieval via Chainlit API

#### Database Schema (FR-007, FR-008, FR-009)
- ~~FR-007: Custom user and chat session tables~~
- ~~FR-008: Complex analytics tracking tables~~
- ~~FR-009: Custom migration for user data~~

**Replace with**:
- FR-007: Use Chainlit standard schema (users, threads, steps, elements, feedbacks)
- FR-008: Simple documents and chunks tables (essential attributes only)
- FR-009: No migration needed (test data only, recreate database)

### Update User Stories

#### User Story 1 - Modern Chat Interface
**Remove**: Email/password signup, password reset flows
**Keep**: OAuth login (Google, GitHub), persistent sessions, conversation history

**Updated Acceptance Scenarios**:
1. **Given** a new user visits the application, **When** they click "Login with Google" or "Login with GitHub", **Then** their account is created and they are logged into a new chat session
2. (Keep existing scenarios 2-4 unchanged)

---

## 2. plan.md Updates

### Remove Infrastructure Components

#### Authentication Stack
- ~~JWT library (python-jose)~~
- ~~Password hashing (bcrypt)~~
- ~~Custom User/ChatSession/Message models~~

**Replace with**:
- Chainlit OAuth configuration
- Chainlit's built-in session management

### Update Technical Dependencies

**Remove**:
```
- python-jose (JWT)
- passlib (password hashing)
- bcrypt
```

**Add**:
```
- Chainlit 1.3.2 with OAuth support
```

### Update Project Structure

**backend/src/models.py**:
```
BEFORE: User, ChatSession, Message, FineTunedModel, Document, Chunk
AFTER:  User, Thread, Step, Element, Feedback (Chainlit), Document, Chunk (simple)
```

**backend/src/main.py**:
```
REMOVE: 
- POST /auth/register
- POST /auth/login  
- POST /auth/forgot-password
- POST /auth/reset-password
- JWT middleware

KEEP:
- GET /health
- GET /health/db
- RAG endpoints
```

---

## 3. tasks.md Updates

### Phase 2: Foundational - Remove Tasks

**Remove**:
- ~~T033 [US1] Implement authentication endpoints (register, login)~~
- ~~T046 [US1] Add JWT token generation and validation~~
- ~~T035 [P] [US1] Implement user profile endpoints (GET /auth/me, POST /auth/logout)~~

**Replace with**:
- T033 [US1] Configure Chainlit OAuth for Google and GitHub
- T034 [US1] Set up Chainlit session management
- T035 [US1] Test OAuth login flow and session persistence

### Phase 3: User Story 1 - Update Tasks

**Remove**:
- ~~T037 [US1] Implement password authentication callback~~

**Replace with**:
- T037 [US1] Configure OAuth providers in frontend/.chainlit/config.toml

### Update Task Counts

**Original**: 167 tasks
**After Simplification**: ~145 tasks (removed 22 auth-related tasks)

### Revised Phase 3 Task List

```markdown
## Phase 3: User Story 1 - Modern Chat Interface with OAuth (Priority: P1)

- [ ] T031 [P] [US1] Create frontend/.chainlit/config.toml with OAuth settings
- [ ] T032 [P] [US1] Create frontend/chainlit_config.py with OAuth credentials
- [ ] T033 [US1] Configure Google OAuth in Chainlit (client ID, secret)
- [ ] T034 [US1] Configure GitHub OAuth in Chainlit (client ID, secret)
- [ ] T036 [US1] Create main Chainlit app in frontend/chainlit.py with @cl.on_chat_start and @cl.on_message
- [ ] T037 [US1] Test OAuth login flow with Google and GitHub
- [ ] T038 [P] [US1] Implement session persistence using Chainlit's built-in SQLAlchemy data layer
- [ ] T039 [US1] Integrate RAG pipeline with Chainlit message handler
- [ ] T040 [P] [US1] Add streaming response support in Chainlit
- [ ] T041 [P] [US1] Create frontend/components/ with custom UI components
- [ ] T042 [US1] Create frontend/Dockerfile for Chainlit container
- [ ] T043 [US1] Create frontend/docker-compose.yml
- [ ] T044 [US1] Test end-to-end: OAuth login → chat → logout → login → history preserved
```

---

## 4. Quick Reference: What Changed

### Authentication

| Aspect | Before | After |
|--------|--------|-------|
| Method | Email/password + OAuth | OAuth only (Google, GitHub) |
| Storage | Custom User table | Chainlit users table |
| Tokens | JWT | Chainlit session management |
| Endpoints | /auth/register, /auth/login, /auth/reset | None (Chainlit handles) |

### Database

| Table | Before | After |
|-------|--------|-------|
| users | Custom (email, password_hash, oauth_provider, ...) | Chainlit standard (id, identifier, metadata, createdAt) |
| chat_sessions | Custom (user_id, name, created_at, ...) | Chainlit threads (userId, name, metadata, ...) |
| messages | Custom (chat_session_id, role, content, ...) | Chainlit steps (threadId, type, input, output, ...) |
| documents | Complex (many fields) | Simple (id, title, content, source, docType, metadata) |
| chunks | Complex (token_count, overlap_start, ...) | Simple (id, documentId, chunkIndex, content, metadata) |
| fine_tuned_models | Custom table | Removed (track in HuggingFace/W&B) |

### Code Changes

| File | Changes |
|------|---------|
| backend/src/models.py | Use Chainlit models + simple Document/Chunk |
| backend/src/main.py | Remove auth endpoints, keep RAG endpoints |
| backend/alembic/versions/ | New migration: 001_chainlit_schema.py |
| frontend/chainlit.py | Main Chainlit app with OAuth |
| frontend/.chainlit/config.toml | OAuth configuration |

---

## 5. Next Steps

1. ✅ **Database**: Schema updated (DONE)
2. ✅ **Models**: models.py updated (DONE)
3. ✅ **Documentation**: copilot-instructions.md updated (DONE)
4. ⏳ **Spec**: Update spec.md with OAuth-only requirements
5. ⏳ **Plan**: Update plan.md with simplified architecture
6. ⏳ **Tasks**: Update tasks.md with revised task list
7. ⏳ **Code**: Remove auth endpoints from main.py
8. ⏳ **Config**: Set up OAuth in Chainlit

---

## 6. Testing Checklist

After all updates:

- [ ] Database migration runs successfully
- [ ] Models import without errors
- [ ] OAuth login works with Google
- [ ] OAuth login works with GitHub
- [ ] Sessions persist across logins
- [ ] Conversation history loads correctly
- [ ] RAG pipeline integrates with Chainlit
- [ ] No password/JWT code remains

---

## References

- Chainlit OAuth Guide: https://docs.chainlit.io/authentication/oauth
- Chainlit Data Layer: https://docs.chainlit.io/data-layers/sqlalchemy
- Schema Changes: `/specs/001-improve-rag-system/SCHEMA_SIMPLIFICATION.md`
- Updated Constitution: `/.github/copilot-instructions.md`
