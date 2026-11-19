"""FastAPI main application entrypoint for IncidentLens."""

import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import RequestResponseEndpoint

from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.incidents import router as incidents_router
from app.api.v1.endpoints.ingest import router as ingest_router
from app.api.v1.endpoints.logs import router as logs_router
from app.api.v1.endpoints.patterns import router as patterns_router
from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.errors import register_error_handlers
from app.core.logging import request_id_ctx, setup_logging

logger = setup_logging(debug=settings.DEBUG)


def run_database_migrations() -> None:
    """Run database migrations to head on application startup."""
    import os

    if os.getenv("TESTING") == "1" or settings.ENVIRONMENT == "test":
        return

    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    ini_path = Path("alembic.ini")
    if not ini_path.exists():
        ini_path = Path("backend/alembic.ini")

    if not ini_path.exists():
        logger.warning("alembic.ini not found, skipping startup migrations")
        return

    try:
        cfg = Config(str(ini_path))
        script_loc = Path(cfg.get_main_option("script_location", "alembic"))
        if not script_loc.is_absolute():
            script_loc = ini_path.parent / script_loc
        cfg.set_main_option("script_location", str(script_loc))
        cfg.set_main_option("sqlalchemy.url", settings.DATABASE_SYNC_URL)
        command.upgrade(cfg, "head")
        logger.info("Database migrations applied successfully to head.")
    except Exception as exc:
        logger.error(f"Failed to apply database migrations on startup: {exc}", exc_info=True)


async def init_db() -> None:
    """Initialize database tables and vector extension if not present."""
    import os

    if os.getenv("TESTING") == "1" or settings.ENVIRONMENT == "test":
        return

    from sqlalchemy import text

    from app.db.base import Base
    from app.db.session import async_engine

    try:
        async with async_engine.begin() as conn:
            if async_engine.dialect.name == "postgresql":
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables initialized successfully via SQLAlchemy.")
    except Exception as exc:
        logger.error(f"Failed to initialize database tables: {exc}", exc_info=True)

    # Also run Alembic to ensure version metadata is stamped/up-to-date
    run_database_migrations()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context for startup and shutdown events."""
    logger.info(
        f"Starting {settings.PROJECT_NAME} in {settings.ENVIRONMENT} mode (debug={settings.DEBUG})"
    )
    await init_db()
    yield
    logger.info(f"Stopping {settings.PROJECT_NAME}")


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="AI-Powered Incident Log Explainer with Evidence-Linked Root-Cause Reports",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS Middleware (strict allowlists + Vercel support)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Request-ID"],
)


# Request ID Tracing & Security Headers Middleware
@app.middleware("http")
async def request_id_middleware(
    request: Request, call_next: RequestResponseEndpoint
) -> Response:
    incoming_req_id = request.headers.get("X-Request-ID")
    req_id = incoming_req_id or str(uuid.uuid4())
    token = request_id_ctx.set(req_id)
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        if settings.ENVIRONMENT == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response
    except Exception as exc:
        logger.error(f"Unhandled exception in request {req_id}: {exc}", exc_info=True)
        from fastapi.responses import JSONResponse

        origin = request.headers.get("origin")
        err_headers = {
            "X-Request-ID": req_id,
            "X-Content-Type-Options": "nosniff",
        }
        if origin and (
            origin in settings.CORS_ORIGINS
            or origin.endswith(".vercel.app")
            or "localhost" in origin
        ):
            err_headers["Access-Control-Allow-Origin"] = origin
            err_headers["Access-Control-Allow-Credentials"] = "true"
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": str(exc) if settings.DEBUG else "An internal server error occurred",
                    "request_id": req_id,
                }
            },
            headers=err_headers,
        )
    finally:
        request_id_ctx.reset(token)


# Register consistent error handlers
register_error_handlers(app, debug=settings.DEBUG)

# Root-level liveness & readiness probes for Docker/K8s
app.include_router(health_router)

# Mount ingest, logs, patterns, and incidents at root as well to support direct /ingest, /batches/{id}, /incidents/{id}
app.include_router(ingest_router)
app.include_router(logs_router)
app.include_router(patterns_router)
app.include_router(incidents_router)

# Versioned API routes
app.include_router(api_v1_router, prefix=settings.API_V1_PREFIX)
