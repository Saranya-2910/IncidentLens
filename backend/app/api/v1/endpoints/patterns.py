"""Error patterns endpoints."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.error_pattern import ErrorPatternResponse, PaginatedPatternsResponse
from app.services.pattern_service import PatternService

router = APIRouter(tags=["Error Patterns"])


@router.get(
    "/projects/{id}/patterns",
    response_model=PaginatedPatternsResponse,
    summary="List normalized error patterns for a project with trends and samples",
)
async def list_project_patterns(
    id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    level: Annotated[str | None, Query(description="Filter by log level (e.g. ERROR, WARN)")] = None,
    service: Annotated[str | None, Query(description="Filter by originating service")] = None,
    start_time: Annotated[datetime | None, Query(description="Earliest timestamp")] = None,
    end_time: Annotated[datetime | None, Query(description="Latest timestamp")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginatedPatternsResponse:
    pattern_service = PatternService(db)
    patterns, total = await pattern_service.list_patterns(
        user_id=current_user.id,
        project_id=id,
        level=level,
        service=service,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
        offset=offset,
    )
    return PaginatedPatternsResponse(
        items=[ErrorPatternResponse.model_validate(p) for p in patterns],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/projects/{id}/patterns/{pattern_id}",
    response_model=ErrorPatternResponse,
    summary="Get detailed error pattern info with high-resolution trend buckets",
)
async def get_pattern_detail(
    id: uuid.UUID,
    pattern_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ErrorPatternResponse:
    pattern_service = PatternService(db)
    detail = await pattern_service.get_pattern_detail(
        user_id=current_user.id,
        project_id=id,
        pattern_id=pattern_id,
    )
    return ErrorPatternResponse.model_validate(detail)
