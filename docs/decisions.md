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
