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

## Authentication Headers
- For user requests: `Authorization: Bearer <jwt_access_token>` or cookie `access_token`
- For ingestion requests: `X-API-Key: il_live_<prefix>_<secret>`
