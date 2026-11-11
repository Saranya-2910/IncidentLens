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

## ADR 008: Plugin-Style Parser Registry & Stack Trace Assembler
- **Context**: Incoming logs arrive in diverse, heterogeneous formats (JSON lines, Syslog, Spring/Log4j, standard Python) and often include multi-line stack traces (Python, Java, Go).
- **Decision**: Implement a prioritized parser registry (`JsonLinesParser` -> `StandardLogParser` -> `GenericFallbackParser`) wrapped in a streaming state machine (`LogStreamProcessor`) that accumulates whitespace-indented or `Traceback`/`Caused by:` continuation lines onto the preceding event.
- **Why**: Ensures zero data loss, guarantees stack traces remain unified as a single searchable event, and prevents malformed lines from aborting batch ingestion.

## ADR 009: Chunked Bulk Insertion & Idempotent Reprocessing
- **Context**: Uploading 50,000+ line log files line-by-line via ORM sessions causes massive latency and memory consumption, and network failures require safe retries.
- **Decision**: Stream lines from local storage directly without holding the entire file in RAM, bulk insert structured events in chunks of 2,000 using `INSERT ... VALUES`, and purge prior `log_events` for the `batch_id` before inserting.
- **Why**: Achieves sub-5-second ingestion for 50,000 lines while guaranteeing that worker retries are strictly idempotent and never duplicate events.

## ADR 010: Deterministic Synthetic Dataset Generator and One-Click Demo Seeding
- **Context**: Evaluating incident root-cause explainers requires realistic, ground-truth-labeled log datasets across varied failure modes (resource exhaustion, bad deploys, cascading timeouts, external dependency failures) with controlled noise levels and single vs multi-service cascades. Evaluators also need immediate one-click testing in the UI without manually preparing log files.
- **Decision**: Implement a standalone deterministic generator (`simulator/generate.py`) supporting 8 scenario categories x 4 variants (low/high noise x single/multi-service) + 2 control datasets (healthy steady-state and benign traffic spike) = 34 scenarios. Pair this with a project-scoped seeding endpoint (`POST /projects/{id}/demo-data`) and catalog endpoint (`GET /projects/demo-scenarios`).
- **Why**: Enables 100% reproducible offline benchmark evaluation with ground-truth verification, tests both single-service and multi-service cascading failures with multi-line stack traces, and lets evaluators explore the system instantly with zero configuration.

## ADR 011: Token Masking, Stack Trace Signatures, and Idempotent Pattern Grouping
- **Context**: Thousands of log lines in production incidents differ only by ephemeral tokens (UUIDs, IP addresses, transaction numbers, thread addresses, timestamps). Furthermore, hashing raw multi-line stack traces directly fragments patterns whenever line numbers change between code revisions.
- **Decision**: Implement a deterministic regex-based normaliser that masks variable tokens into standardized placeholders (`<UUID>`, `<NUM>`, `<IP>`, `<HOST>`, `<PATH>`, `<NUM>ms`, `'<STR>'`) and extracts stack trace signatures based on the normalized exception line plus the top application call frames (`basename.py:function_name`), ignoring line numbers. Group events by project-scoped fingerprints (`SHA-256(level:template)`) inside a post-parsing Celery worker step (`PatternGrouper`) with atomic upserts and count reconciliation.
- **Why**: Collapses thousands of repetitive log lines into a tiny set of meaningful error patterns (>98% reduction ratio on simulated incident datasets) while maintaining idempotent batch reprocessing and fast database queries.
