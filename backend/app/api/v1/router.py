"""API v1 router registry."""

from fastapi import APIRouter

from app.api.v1.endpoints import health

api_v1_router = APIRouter()

# Include health routes in /api/v1 as well
api_v1_router.include_router(health.router)
