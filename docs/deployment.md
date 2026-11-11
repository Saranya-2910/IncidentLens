# IncidentLens Deployment Guide

This guide covers running IncidentLens locally via Docker Compose and deploying to production cloud hosting (**Render / Railway** for the FastAPI API + Celery Worker + Postgres + Redis, and **Vercel** for the React frontend).

---

## 1. Local All-in-One Docker Compose

Prerequisites: Docker Desktop / Docker Engine with Compose v2.

1. Copy `.env.example` to `.env` and optionally add your `GEMINI_API_KEY`:
   ```bash
   cp .env.example .env
   ```
   *(If `GEMINI_API_KEY` is omitted, IncidentLens runs cleanly with its offline fallback/fake client for pipeline testing).*

2. Start all 5 services (`postgres` with pgvector, `redis`, `api`, `worker`, and `frontend`):
   ```bash
   docker compose up --build -d
   ```

3. Access the platform:
   - **Frontend Dashboard**: http://localhost:3000
   - **Backend OpenAPI Swagger UI**: http://localhost:8000/docs
   - **Health / Readiness**: http://localhost:8000/health and http://localhost:8000/ready

---

## 2. Cloud Production Deployment

### A. Backend, Worker, Postgres (pgvector), and Redis on Render (or Railway)

A ready-to-use Blueprint manifest is included at [`render.yaml`](../render.yaml).

1. **Managed PostgreSQL + pgvector**:
   - Provision a PostgreSQL 16 instance (Render Postgres, Neon, Supabase, or Railway Postgres) with the `vector` (`pgvector`) extension supported.
   - Note: `alembic/versions/0001_enable_pgvector.py` executes `CREATE EXTENSION IF NOT EXISTS vector;` automatically on first run.
2. **Managed Redis**:
   - Provision a Redis instance for Celery task brokering and login/ingest rate limiting.
3. **API Web Service (`incidentlens-api`)**:
   - Root/Docker context: repository root, Dockerfile: `backend/Dockerfile`.
   - Start Command: `sh -c "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT"`
   - Mount a persistent disk at `/app/storage` if sharing raw uploads with the worker service.
4. **Background Worker Service (`incidentlens-worker`)**:
   - Same Dockerfile `backend/Dockerfile`.
   - Start Command: `celery -A app.workers.celery_app.celery_app worker -B --loglevel=info` (`-B` runs the daily retention cleanup schedule).

### B. Frontend Dashboard on Vercel

1. Import the repository in Vercel and set **Root Directory** to `frontend`.
2. Build settings (detected automatically):
   - **Framework Preset**: Vite
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`
3. Set Environment Variable in Vercel Project Settings:
   - `VITE_API_URL=https://<your-render-api-domain>.onrender.com/api/v1`
4. `frontend/vercel.json` is configured with SPA rewrites so client-side routes refresh cleanly.

---

## 3. Environment Variables Reference

| Variable | Description | Required (Prod) | Default / Example |
| :--- | :--- | :---: | :--- |
| `ENVIRONMENT` | Runtime mode (`development`, `production`) | Yes | `production` |
| `DEBUG` | Enable verbose debug errors (must be `false` in prod) | Yes | `false` |
| `SECRET_KEY` | JWT signing secret (min 32 random bytes) | Yes | `<random-32-byte-secret>` |
| `CORS_ORIGINS` | JSON array or comma-separated allowed frontend URLs | Yes | `["https://incidentlens.vercel.app"]` |
| `DATABASE_URL` | PostgreSQL connection URI (auto-normalizes `postgres://` to `+asyncpg`) | Yes | `postgresql+asyncpg://...` |
| `DATABASE_SYNC_URL` | Sync PostgreSQL URI for Alembic & Celery (`+psycopg`) | Yes | `postgresql+psycopg://...` |
| `REDIS_URL` | Redis URL for rate limiting | Yes | `redis://...` |
| `CELERY_BROKER_URL` | Redis broker URL for Celery | Yes | `redis://...` |
| `CELERY_RESULT_BACKEND` | Redis result backend URL | Yes | `redis://...` |
| `GEMINI_API_KEY` | Google Gemini API key (strictly backend-only) | Yes (live AI) | `<your-gemini-api-key>` |
| `GEMINI_MODEL` | Gemini model identifier | No | `gemini-2.0-flash` |
| `EMBEDDING_MODEL` | Gemini embedding model | No | `text-embedding-004` |
| `EMBEDDING_DIMENSION` | Embedding vector size (pgvector column dim) | No | `768` |
| `SIMILARITY_THRESHOLD` | Minimum cosine similarity for similar incidents | No | `0.45` |
| `EVENT_RETENTION_DAYS` | Retention period in days before automatic cleanup | No | `30` |

---

## 4. Database Migrations

All schema changes are tracked cleanly with Alembic in `backend/alembic/versions/`:
```bash
cd backend
alembic upgrade head
```
To verify current migration revision:
```bash
alembic current
```
