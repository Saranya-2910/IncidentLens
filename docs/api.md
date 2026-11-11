# IncidentLens API Documentation

All versioned API endpoints are prefixed with `/api/v1` except for root health and readiness probes.

## Health Probes
- `GET /health`: Liveness probe (200 OK)
- `GET /ready`: Readiness probe verifying database connectivity (200 OK or 503)

## Authentication (`/api/v1/auth`)
- `POST /api/v1/auth/register`: Create user account. Returns `{ "access_token": "...", "token_type": "bearer", "user": { ... } }` and sets HttpOnly cookie.
- `POST /api/v1/auth/login`: Authenticate with email and password. Protected by rate limiting (max 5 requests/min per IP). Returns token and sets HttpOnly cookie.
- `POST /api/v1/auth/logout`: Log out and clear session cookie.
- `GET /api/v1/auth/me`: Retrieve current authenticated user profile. Requires Bearer token or HttpOnly cookie.

## Project Management (`/api/v1/projects`)
All project operations are strictly scoped to the authenticated user.
- `POST /api/v1/projects`: Create a project. Body: `{ "name": "...", "description": "..." }`. Returns 201.
- `GET /api/v1/projects`: List all projects owned by current user.
- `GET /api/v1/projects/{id}`: Get project details. Returns 404 if project does not exist or belongs to another user.
- `PATCH /api/v1/projects/{id}`: Update project name or description. Returns 404 if not owned.
- `DELETE /api/v1/projects/{id}`: Delete project and cascade-delete its API keys and logs. Returns 204.

## Ingestion API Keys (`/api/v1/projects/{id}/api-keys`)
- `POST /api/v1/projects/{id}/api-keys`: Create a new ingestion API key. Body: `{ "label": "..." }`. Returns 201 with `raw_key` shown **only once**.
- `GET /api/v1/projects/{id}/api-keys`: List API keys for project (prefix and metadata only; raw keys are never stored or returned).
- `DELETE /api/v1/projects/{id}/api-keys/{key_id}`: Revoke an API key. Revoked keys are rejected immediately by ingestion endpoints.

## Log Ingestion & Batches
- `POST /api/v1/projects/{id}/logs/upload`: Multipart file upload (supports `.log`, `.txt`, `.json`, `.ndjson`). Maximum size 50 MB. Dispatches asynchronous Celery worker and returns `202 Accepted` with `batch_id`.
- `POST /ingest` (also `/api/v1/ingest`): Direct HTTP ingestion of log lines using `X-API-Key` authentication. Accepts raw NDJSON, JSON array of objects, or plain text. Size limit 10 MB. Returns `202 Accepted` with `batch_id`.
- `GET /api/v1/projects/{id}/batches`: List log batches for an owned project (status, line count, errors).
- `GET /api/v1/batches/{id}` (also `/batches/{id}`): Get status and error details for a specific batch. Returns 404 if not owned.

## Events Search (`/api/v1/projects/{id}/events`)
Search and filter parsed log events strictly scoped to the owned project:
- `service`: Filter by originating service name.
- `level`: Filter by log severity (`INFO`, `WARN`, `ERROR`, `FATAL`, `DEBUG`).
- `start_time` / `end_time`: Filter within UTC time bounds (ISO 8601).
- `pattern_id`: Filter by associated error pattern ID.
- `text`: Substring match on event message.
- `limit` (default 50) and `offset` (default 0) pagination.

## Error Patterns (`/api/v1/projects/{id}/patterns`)
- `GET /api/v1/projects/{id}/patterns`: List collapsed, normalized error patterns for an owned project. Query filters: `level`, `service`, `start_time`, `end_time`, `limit`, `offset`. Each pattern item contains `id`, `fingerprint`, `template`, `level`, `total_count`, `first_seen`, `last_seen`, `example_event_ids`, and `trend` (hourly frequency buckets).
- `GET /api/v1/projects/{id}/patterns/{pattern_id}`: Retrieve detailed pattern metrics including high-resolution 10-minute trend buckets and sample events. Returns 404 if not found or unowned.

## Incidents & Origin Detection (`/api/v1/projects/{id}/incidents`)
- `GET /api/v1/projects/{id}/incidents`: List detected incidents for an owned project. Filters: `status` (`open`, `resolved`), `severity` (`critical`, `high`, `medium`, `low`), `limit`, `offset`. Returns incident window bounds, severity, `affected_services`, `event_count`, and `origin_pattern_id`.
- `GET /api/v1/incidents/{id}` (also `/api/v1/projects/{id}/incidents/{incident_id}`): Retrieve full incident detail including chronological event `timeline` across services, linked `patterns`, and ranked `origin_candidates` with scoring reasons. Returns 404 if not owned.

## Demo Datasets & Seeding
- `GET /api/v1/projects/demo-scenarios`: List all 34 pre-generated incident scenarios with ground-truth metadata, noise levels, and expected key patterns.
- `POST /api/v1/projects/{id}/demo-data`: Seed an owned project with a simulated incident dataset for instant evaluation. Body: `{ "scenario_id": "db_pool_exhaustion_low_noise_multi_service" }` (optional, defaults to database connection pool exhaustion). Returns `202 Accepted` with `batch_id` and queues background processing. Returns 404 if project is not owned.

## Authentication Headers
- For user requests: `Authorization: Bearer <jwt_access_token>` or cookie `access_token`
- For ingestion requests: `X-API-Key: il_live_<prefix>_<secret>`
