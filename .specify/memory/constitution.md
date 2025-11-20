<!--
Sync Impact Report:
Version Change: 2.0.0 → 2.1.0
Modified Principles:
  - Technology Stack: Added PostgreSQL 18, removed password auth references
  - Schema Simplification: Adopt Chainlit standard schema (users, threads, steps, elements, feedbacks)
  - Authentication: OAuth only (Google, GitHub) - no passwords, no JWT
Added Sections:
  - Database simplification principle
  - OAuth-only authentication rationale
Removed Sections:
  - JWT and password authentication references
Templates Status:
  - ✅ plan-template.md: Constitution checks aligned with simplified architecture
  - ✅ spec-template.md: Requirements compatible with Chainlit integration
  - ✅ tasks-template.md: Task organization supports modular implementation
  - ✅ copilot-instructions.md: Schema simplification documented
Follow-up TODOs:
  - Update /specs/001-improve-rag-system/spec.md with schema changes
  - Update /specs/001-improve-rag-system/plan.md with OAuth approach
  - Update /specs/001-improve-rag-system/tasks.md with simplified tasks
-->

# Vietnamese Medical RAG QA System Constitution

## Core Principles

### I. MVP First - Production Later

**MUST** prioritize working functionality over production-grade standards during MVP phase.

- Features must be functional and stable, but perfect is the enemy of done
- Production-grade standards (comprehensive testing, environment separation, extensive documentation) are deferred
- Code quality matters, but MVP speed takes precedence
- Legacy code markers MUST be used when replacing working implementations

**Rationale**: As an MVP project, rapid iteration and feature validation are more valuable than premature optimization. We maintain stable functionality while allowing flexibility to evolve architecture.

### II. Modular Architecture

**MUST** organize code into focused, single-purpose modules.

- Each file implements one cohesive set of related functions
- Clear separation between services, models, configurations, and core utilities
- Backend follows `backend/src/{services,core,configs,schemas,functions}` structure
- Frontend isolated in dedicated `frontend/` directory with Streamlit UI
- No monolithic files - if a module grows beyond 300 lines, consider splitting

**Rationale**: Modular structure ensures code remains maintainable and understandable as the system evolves. Clear boundaries prevent cognitive overload.

### III. No Test-Driven Development (MVP Exception)

**MUST NOT** create tests during MVP implementation phase.

- TDD and comprehensive testing are explicitly deferred
- Focus development effort on feature delivery
- Code must still be written defensively (error handling, validation)
- Testing infrastructure can be added post-MVP

**Rationale**: For MVP velocity, testing overhead is postponed. The system must still be robust through proper error handling, but formal test suites are not required.

### IV. Minimal Documentation

**MUST** keep documentation concise and purpose-driven.

- Avoid lengthy comments and annotations in code
- Self-documenting code preferred over verbose explanations
- Technical docs (specs, plans, tasks) MUST be in English for AI model context
- User-facing docs (if needed) in Vietnamese
- Store documentation in `/docs` folder only when essential
- Avoid redundant summaries and obvious explanations

**Rationale**: Over-documentation slows MVP iteration. Code clarity and minimal strategic docs provide sufficient context.

### V. Working Code Over Perfect Code

**MUST** prioritize functional, simple solutions over architectural elegance.

- If existing code works, prefer extending over rewriting
- Mark replaced implementations as "legacy code" with clear comments
- Avoid premature abstractions and design patterns
- YAGNI principle: implement only what's needed now
- Refactoring is acceptable but not required during MVP phase

**Rationale**: MVP success depends on delivering value quickly. Elegant architecture can be refined after product-market fit validation.

### VI. Async Task Execution

**MUST** leverage Celery for long-running operations.

- RAG query processing handled asynchronously via `message_handler_task`
- Document chunking and indexing via `chunk_and_index_document` task
- Redis used as Celery broker and result backend
- Support both sync (`is_sync_request=True`) and async endpoints
- Worker container runs independently from API container

**Rationale**: Medical RAG queries involve embedding generation, vector search, reranking, and LLM completion - operations that block HTTP responses. Async execution ensures API responsiveness.

### VII. Observability Through Structured Logging

**MUST** use structured logging for debugging and monitoring.

- Loguru configured across backend services
- Log key decision points: route detection, RAG vs web search, reranking scores
- Include conversation IDs and user context in logs
- Error logs MUST include full exception traces
- No silent failures

**Rationale**: As an MVP without monitoring infrastructure, logs are the primary observability tool. Structured logs enable quick debugging and issue diagnosis.

## Technology Stack & Constraints

### Required Stack

- **Language**: Python 3.12
- **Backend Framework**: FastAPI 0.112.2
- **Frontend**: Chainlit 1.3.2 (RAG-native UI with OAuth authentication)
- **Database**: PostgreSQL 18 (Chainlit standard schema)
- **Vector DB**: Qdrant 1.10.1
- **Cache/Queue**: Redis 5.0.7 (with Celery 5.4.0)
- **Search**: Elasticsearch 8.11.0 (BM25 keyword search)
- **LLM Provider**: OpenAI (gpt-4o-mini, text-embedding-3-small), Deepseek (chat, reasoner)
- **Reranking**: Cohere (rerank-v3.5)
- **Deployment**: Docker Compose with separate containers (API, Worker, DBs)

**Frontend Framework Rationale**: Chainlit 1.3.2 provides:

- Native RAG features (streaming responses, conversation history, session management)
- Built-in OAuth authentication (Google, GitHub) - no password complexity
- Persistent chat sessions with standard SQLAlchemy schema
- Superior UX for medical consultation workflows
- Eliminates need for custom User/ChatSession/Message tables

**Database Schema Approach**:

- Use Chainlit standard schema (users, threads, steps, elements, feedbacks) for chat functionality
- Keep separate simple tables for medical content (documents, chunks)
- No custom authentication tables - OAuth handled by Chainlit
- No JWT tokens - session management built-in
- Reference: [Chainlit Data Layer Documentation](https://docs.chainlit.io/data-layers/sqlalchemy)

### External Services

- OpenAI API for embeddings and chat completion
- Deepseek API for alternative reasoning
- Cohere API for reranking
- Tavily API for web search fallback

### Environment Management

**MUST** use single `.env` file for all configuration.

- No environment separation (dev/staging/prod) during MVP
- Sensitive keys in `.env` (never commit)
- `.env.example` provided as template
- Configuration loaded via `pydantic-settings`

## Development Workflow

### Code Organization

- Backend logic in `backend/src/`
- Frontend in `frontend/`
- Database migrations in `backend/alembic/`
- Docker compose files at module level (`backend/docker-compose.yml`, `database/docker-compose.yml`, `frontend/docker-compose.yml`)

### Implementation Phases

Each feature implementation follows this flow:

1. **Spec**: Define requirements in `.specify/specs/[feature]/spec.md`
2. **Plan**: Research and design in `plan.md`, `research.md`, `data-model.md`
3. **Tasks**: Break into actionable tasks in `tasks.md`
4. **Implement**: Write code, mark legacy implementations if replacing
5. **Verify**: Manual testing and validation (no automated tests required)
6. **Summary**: Brief bullet-point summary of changes and setup steps

### Legacy Code Handling

When replacing working code:

- **MUST** mark old implementation with `# LEGACY CODE - replaced by [new_module]` comment
- Do not delete immediately (allows rollback if new code fails)
- Document reason for replacement in comment
- Remove legacy code only after new implementation proven stable

### Commit Practices

- Commit frequently at logical checkpoints
- Descriptive commit messages following conventional commits format (`feat:`, `fix:`, `refactor:`, `docs:`)
- No strict review process during MVP (team discretion)

## Governance

### Constitution Authority

This constitution defines the development principles for the Vietnamese Medical RAG QA System MVP phase. All feature planning, task generation, and implementation decisions MUST align with these principles.

### Amendments

- Constitution changes require explicit discussion and approval
- Version incremented following semantic versioning:
  - **MAJOR**: Fundamental principle changes (e.g., adding mandatory testing)
  - **MINOR**: New principles or significant expansions
  - **PATCH**: Clarifications, wording improvements, minor corrections
- Amendment date tracked in version footer

### Compliance

- All PRs reviewed against constitution principles (automated via `.github/prompts/speckit.*.md`)
- Complexity violations MUST be justified in `plan.md` Complexity Tracking section
- When principles conflict, prioritize: MVP First → Working Code → Modular Architecture

### Future Transition

When MVP transitions to production:

- Testing principles will be added (TDD, integration tests)
- Environment separation will be required
- Documentation standards will increase
- This constitution will be amended to v3.0.0

**Version**: 2.1.0 | **Ratified**: 2025-10-29 | **Last Amended**: 2025-11-15

**Changelog**:

- **v2.1.0** (2025-11-15): MINOR - Added PostgreSQL 18, schema simplification (Chainlit standard), OAuth-only authentication
- **v2.0.0** (2025-10-31): MAJOR - Updated frontend framework from Streamlit to Chainlit 1.3.2 for RAG-native features
- **v1.0.0** (2025-10-29): Initial constitution ratification

```markdown
<!-- End of Constitution -->
```
