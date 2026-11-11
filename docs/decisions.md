# Architectural Decision Records (ADRs)

## ADR 001: Monolithic FastAPI Backend with Celery Worker
- **Context**: IncidentLens processes log files, extracts patterns, clusters incidents, and communicates with LLMs. Heavy log parsing and LLM calls should never block the web request path.
- **Decision**: Use a layered FastAPI application for the synchronous and async REST API endpoints, paired with Celery + Redis for asynchronous background tasks.
- **Why**: Keeps deployment simple (two container services from one codebase), avoids HTTP request timeouts on large 50k+ line log uploads, and provides built-in retry mechanisms and task queues.

## ADR 002: Dual Engine Database Strategy (AsyncPG + Psycopg)
- **Context**: FastAPI benefits from async I/O (`asyncpg`) to avoid thread pooling overhead during concurrent user requests, while Celery tasks and Alembic migrations traditionally operate synchronously and reliably with `psycopg3`.
- **Decision**: Configure SQLAlchemy 2.0 with both async session factories (`asyncpg`) for FastAPI dependencies and sync session engines (`psycopg`) for Celery workers and Alembic migrations.
- **Why**: Maximizes API throughput without encountering event-loop conflicts inside Celery worker threads or Alembic CLI execution.

## ADR 003: Deterministic Pipeline Before LLM
- **Context**: Passing thousands of raw log lines directly into an LLM context is expensive, slow, non-deterministic, and susceptible to prompt injection.
- **Decision**: All parsing, variable token masking (normalisation), fingerprinting, baseline calculation, and incident clustering are done deterministically in code before invoking Gemini.
- **Why**: Reduces LLM context token usage by 90%+, drastically lowers latency and cost, and limits the attack surface for prompt injections.

## ADR 004: Strict Evidence Verification
- **Context**: LLMs can hallucinate causes and cite non-existent evidence or unrelated logs.
- **Decision**: The backend numbers log lines presented to the model (e.g. `L1`, `L2`) and verifies every citation in the generated response against actual event IDs stored in the database. Any claim with an invalid or missing citation is visibly marked as `unsupported`.
- **Why**: Ensures absolute trustworthiness in root-cause reporting for production incidents.

## ADR 005: Argon2id Password Hashing & Dual JWT/Cookie Auth
- **Context**: Modern authentication requires resisting GPU-assisted dictionary attacks while serving both Single Page Applications (React) and potential external CLI/API clients.
- **Decision**: Use Argon2id (memory-hard, resistant to side-channel and GPU attacks) for passwords. On authentication, return a signed JWT bearer token and set an HttpOnly `SameSite=Lax` cookie.
- **Why**: Eliminates plaintext credential risk, resists brute-forcing, and provides flexibility for browsers (cookie-based sessions) and automated testing/API clients (Bearer header).

## ADR 006: 404 Not Found for Unowned Resources (Anti-Enumeration)
- **Context**: In multi-tenant environments, returning `403 Forbidden` for another user's project or API key leaks the existence of that resource to an attacker.
- **Decision**: Every query for a user-owned resource is scoped with `WHERE user_id = :current_user_id`. If no match is found, return `404 Not Found`.
- **Why**: Protects user privacy and prevents malicious attackers from enumerating valid project IDs or key IDs.

## ADR 007: Ingestion API Key Prefixing and SHA-256 Hashing
- **Context**: High-throughput log ingestion requires fast API key lookup without storing raw secret keys in the database.
- **Decision**: Generate API keys with format `il_live_<prefix8>_<secret32>`. Store only `key_prefix` (indexed for O(1) candidate lookup) and the SHA-256 hash. The raw key is displayed to the user exactly once.
- **Why**: If the database is compromised, attacker cannot reconstruct raw ingestion keys, yet ingestion lookup remains sub-millisecond without scanning the entire table.
