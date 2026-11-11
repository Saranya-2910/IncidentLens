# IncidentLens API Documentation

All API endpoints are prefixed with `/api/v1` except for root health and readiness probes.

## Core Endpoints
- `GET /health`: Liveness probe (returns 200 OK)
- `GET /ready`: Readiness probe (confirms database connectivity)
- `GET /api/v1/health`: Liveness probe
- `GET /api/v1/ready`: Readiness probe
