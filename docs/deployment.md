# IncidentLens Deployment Guide

This guide covers:
1. **Free-Tier Cloud Deployment** (**Render Free** backend + **Supabase Free** PostgreSQL/pgvector + **Vercel Free** frontend)
2. **Local All-in-One Docker Compose**
3. **Optional Scaled Cloud Deployment** (separate Redis + Celery worker)

---

## 1. Free-Tier Cloud Deployment (Render + Supabase + Vercel — \$0/month)

On free tiers, Render does **not** include free background workers (`type: worker`) or persistent disks. IncidentLens supports `TASK_DISPATCH_MODE=inline` and `REDIS_URL=memory://`, allowing the single **Render Free Web Service** to process log batches and AI reports in-process threads with **zero Redis server** and **zero separate worker service**, while storing all parsed events, patterns, incidents, and pgvector embeddings permanently in **Supabase**.

### Step A: Provision Free Database on Supabase (PostgreSQL + pgvector)

1. Create a free project in [Supabase](https://supabase.com/).
2. Open **Connect** → **Session Pooler** (important: choose **Session pooler**, **IPv4**, port **`5432`** — **not** the Direct `db.<ref>.supabase.co` IPv6 URI, because Render Free instances are IPv4-only; also avoid Transaction Pooler port `6543` for Alembic migrations).
3. Copy your Session Pooler URI (with your database password filled in):
   ```text
   postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require
   ```
   *(IncidentLens automatically normalizes `postgresql://` and `?sslmode=require` into `+asyncpg` / `?ssl=require` for FastAPI and `+psycopg` / `?sslmode=require` for Alembic & background tasks.)*
   - Note: Alembic migration `0001_enable_pgvector.py` executes `CREATE EXTENSION IF NOT EXISTS vector;` automatically (supported natively on Supabase).

### Step B: Deploy Backend on Render Free (`incidentlens-api`)

1. Either deploy via **New + → Blueprint** using [`render.yaml`](../render.yaml), **or** create a **Web Service** manually in Render connected to your GitHub repo:
   - **Plan**: `Free`
   - **Language / Runtime**: `Docker`
   - **Root Directory**: *(leave empty)*
   - **Dockerfile Path**: `./backend/Dockerfile`
   - **Docker Build Context Directory**: `.`
   - **Health Check Path**: `/health`
   - **Docker Command**: *(leave empty — `backend/Dockerfile` runs `alembic upgrade head` and starts `uvicorn` on `$PORT` automatically)*
2. Set these **Environment Variables** in Render:
   - `ENVIRONMENT=production`
   - `DEBUG=false`
   - `SECRET_KEY=<32+ char random string>` *(auto-generated if using Blueprint)*
   - `TASK_DISPATCH_MODE=inline`
   - `REDIS_URL=memory://`
   - `CELERY_BROKER_URL=memory://`
   - `CELERY_RESULT_BACKEND=cache+memory://`
   - `DATABASE_URL=<your Supabase Session Pooler URI>`
   - `DATABASE_SYNC_URL=<your Supabase Session Pooler URI>`
   - `CORS_ORIGINS=["https://<your-vercel-app>.vercel.app"]` *(update after Step C once you have the Vercel domain)*
   - `GEMINI_API_KEY=<your-gemini-api-key>` *(optional — runs deterministic offline AI if omitted)*
   - `GEMINI_MODEL=gemini-2.0-flash`
   - `EMBEDDING_MODEL=text-embedding-004`
   - `EVENT_RETENTION_DAYS=30`

3. Deploy and verify `https://<your-render-service>.onrender.com/ready` returns `{"status":"ready","database":"connected"}`.

### Step C: Deploy Frontend on Vercel Free

1. Import the repository in [Vercel](https://vercel.com/) and set **Root Directory** to `frontend`.
2. Build settings (auto-detected from Vite):
   - **Framework Preset**: `Vite`
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`
3. Add Environment Variable in Vercel:
   ```env
   VITE_API_URL=https://<your-render-service>.onrender.com/api/v1
   ```
4. Deploy. [`frontend/vercel.json`](../frontend/vercel.json) handles SPA fallback routing automatically.
5. Copy your `https://<your-app>.vercel.app` URL back into Render's `CORS_ORIGINS` env var (`["https://<your-app>.vercel.app"]`) and redeploy/save on Render.

### Free-Tier Notes & Trade-Offs
- **Cold Starts**: Render Free spins down after 15 minutes of inactivity (~30–50s wake-up on the first request).
- **Ephemeral Disk**: Render Free does not persist local files across restarts, which is fine in `inline` mode because uploaded files are immediately parsed and persisted into Supabase PostgreSQL (`log_events`, `error_patterns`, `incidents`, `incident_reports`).
- **Retention Cleanup**: Without Celery Beat running in a separate worker, trigger cleanup on demand via `POST /api/v1/projects/{id}/events/retention-cleanup` (or schedule an external free cron webhook).

---

## 2. Local All-in-One Docker Compose

Prerequisites: Docker Desktop / Docker Engine with Compose v2.

1. Copy `.env.example` to `.env` and optionally add your `GEMINI_API_KEY`:
   ```bash
   cp .env.example .env
   ```
2. Start all 5 services (`postgres` with pgvector, `redis`, `api`, `worker`, and `frontend`):
   ```bash
   docker compose up --build -d
   ```
3. Access the platform:
   - **Frontend Dashboard**: http://localhost:3000
   - **Backend OpenAPI Swagger UI**: http://localhost:8000/docs
   - **Health / Readiness**: http://localhost:8000/health and http://localhost:8000/ready

---

## 3. Scaling Later (Dedicated Celery Worker + Redis)

When moving beyond free tier to handle high concurrent ingestion volumes:
1. Provision a Redis 7 instance with `maxmemory-policy noeviction`.
2. Set `TASK_DISPATCH_MODE=celery` and point `REDIS_URL`, `CELERY_BROKER_URL`, and `CELERY_RESULT_BACKEND` to your Redis URL.
3. Run a worker container (`celery -A app.workers.celery_app.celery_app worker -B --loglevel=info`) sharing storage (or using S3/R2 object storage).

---

## 4. Environment Variables Reference

| Variable | Description | Default / Free-Tier Value |
| :--- | :--- | :--- |
| `ENVIRONMENT` | Runtime mode (`development`, `production`) | `production` |
| `DEBUG` | Enable verbose debug errors (must be `false` in prod) | `false` |
| `SECRET_KEY` | JWT signing secret (min 32 random bytes) | `<random-32-byte-secret>` |
| `CORS_ORIGINS` | JSON array or comma-separated allowed frontend URLs | `["https://<app>.vercel.app"]` |
| `TASK_DISPATCH_MODE` | `celery` (Redis worker) or `inline` (single-container free tier) | `inline` (free) / `celery` |
| `DATABASE_URL` | PostgreSQL connection URI (auto-normalizes `postgres://` & `sslmode` -> `+asyncpg` / `ssl`) | Supabase Session Pooler URI |
| `DATABASE_SYNC_URL` | Sync PostgreSQL URI for Alembic & tasks (`+psycopg` / `sslmode`) | Supabase Session Pooler URI |
| `REDIS_URL` | Redis URL or `memory://` when running inline | `memory://` (free) |
| `CELERY_BROKER_URL` | Redis broker URL or `memory://` | `memory://` (free) |
| `CELERY_RESULT_BACKEND` | Redis result backend or `cache+memory://` | `cache+memory://` (free) |
| `GEMINI_API_KEY` | Google Gemini API key (strictly backend-only) | `<your-gemini-api-key>` |
| `GEMINI_MODEL` | Gemini model identifier | `gemini-2.0-flash` |
| `EMBEDDING_MODEL` | Gemini embedding model | `text-embedding-004` |
| `EMBEDDING_DIMENSION` | Embedding vector size (`pgvector` column dim) | `768` |
| `SIMILARITY_THRESHOLD` | Minimum cosine similarity for similar incidents | `0.45` |
| `EVENT_RETENTION_DAYS` | Retention period in days before cleanup | `30` |

---

## 5. Database Migrations

All schema changes are tracked in `backend/alembic/versions/`:
```bash
cd backend
alembic upgrade head
```
To verify the current migration revision:
```bash
alembic current
```
