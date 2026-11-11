"""Incident list, detail, and timeline endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.incident import (
    IncidentDetailResponse,
    IncidentResponse,
    PaginatedIncidentsResponse,
)
from app.services.incident_service import IncidentService

router = APIRouter(tags=["Incidents"])


@router.get(
    "/projects/{id}/incidents",
    response_model=PaginatedIncidentsResponse,
    summary="List clustered incidents for an owned project",
)
async def list_project_incidents(
    id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    status: Annotated[str | None, Query(description="Filter by incident status (open, resolved)")] = None,
    severity: Annotated[str | None, Query(description="Filter by severity (critical, high, medium, low)")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginatedIncidentsResponse:
    incident_service = IncidentService(db)
    incidents, total = await incident_service.list_incidents(
        user_id=current_user.id,
        project_id=id,
        status=status,
        severity=severity,
        limit=limit,
        offset=offset,
    )
    items = []
    for inc in incidents:
        inc_resp = IncidentResponse.model_validate(inc)
        if inc.origin_pattern:
            inc_resp.origin_pattern_template = inc.origin_pattern.template
        items.append(inc_resp)

    return PaginatedIncidentsResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/incidents/{id}",
    response_model=IncidentDetailResponse,
    summary="Get incident detail with timeline and origin candidate rankings",
)
async def get_incident_by_id(
    id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> IncidentDetailResponse:
    incident_service = IncidentService(db)
    detail = await incident_service.get_incident_by_id_only(current_user.id, id)
    return IncidentDetailResponse.model_validate(detail)


@router.get(
    "/projects/{project_id}/incidents/{incident_id}",
    response_model=IncidentDetailResponse,
    summary="Get incident detail scoped to project",
)
async def get_project_incident_detail(
    project_id: uuid.UUID,
    incident_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> IncidentDetailResponse:
    incident_service = IncidentService(db)
    detail = await incident_service.get_incident_detail(current_user.id, project_id, incident_id)
    return IncidentDetailResponse.model_validate(detail)
