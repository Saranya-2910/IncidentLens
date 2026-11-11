"""Health and readiness probe endpoints."""

from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from app.db.session import check_db_health

router = APIRouter(tags=["Health"])


class HealthResponse(BaseModel):
    status: str
    service: str = "incidentlens-api"


class ReadyResponse(BaseModel):
    status: str
    database: str


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Liveness probe to confirm the API server process is responding."""
    return HealthResponse(status="ok")


@router.get("/ready", response_model=ReadyResponse, responses={503: {"model": ReadyResponse}})
async def readiness_check(response: Response) -> ReadyResponse:
    """Readiness probe to confirm database connectivity."""
    db_ok = await check_db_health()
    if not db_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadyResponse(status="not_ready", database="disconnected")

    return ReadyResponse(status="ready", database="connected")
