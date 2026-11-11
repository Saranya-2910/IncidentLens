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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context for startup and shutdown events."""
    logger.info(
        f"Starting {settings.PROJECT_NAME} in {settings.ENVIRONMENT} mode (debug={settings.DEBUG})"
    )
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

# CORS Middleware (strict allowlists)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
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
