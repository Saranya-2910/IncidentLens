"""Log upload, batch status, and event search endpoints."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.log_batch import BatchUploadResponse, LogBatchResponse
from app.schemas.log_event import LogEventResponse, PaginatedLogEventsResponse
from app.services.log_service import LogService

router = APIRouter(tags=["Logs & Ingestion"])


@router.post(
    "/projects/{id}/logs/upload",
    response_model=BatchUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a raw log file for background processing",
)
async def upload_log_file(
    id: uuid.UUID,
    file: Annotated[UploadFile, File(description="Application log file (plain text, JSON lines, NDJSON)")],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BatchUploadResponse:
    log_service = LogService(db)
    batch = await log_service.upload_log_file(current_user.id, id, file)
    return BatchUploadResponse(
        batch_id=batch.id,
        status=batch.status,
    )


@router.get(
    "/projects/{id}/batches",
    response_model=list[LogBatchResponse],
    summary="List log batches for a project",
)
async def list_project_batches(
    id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[LogBatchResponse]:
    log_service = LogService(db)
    batches = await log_service.list_batches_for_project(
        current_user.id, id, limit=limit, offset=offset
    )
    return [LogBatchResponse.model_validate(b) for b in batches]


@router.get(
    "/batches/{id}",
    response_model=LogBatchResponse,
    summary="Get ingestion batch status and error details",
)
async def get_batch_details(
    id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LogBatchResponse:
    log_service = LogService(db)
    batch = await log_service.get_batch_by_id(current_user.id, id)
    return LogBatchResponse.model_validate(batch)


@router.get(
    "/projects/{id}/events",
    response_model=PaginatedLogEventsResponse,
    summary="Search and filter parsed log events",
)
async def search_project_events(
    id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    service: Annotated[str | None, Query(description="Filter by originating service")] = None,
    level: Annotated[str | None, Query(description="Filter by log level (e.g. ERROR, WARN)")] = None,
    start_time: Annotated[datetime | None, Query(description="Earliest timestamp (UTC)")] = None,
    end_time: Annotated[datetime | None, Query(description="Latest timestamp (UTC)")] = None,
    pattern_id: Annotated[uuid.UUID | None, Query(description="Filter by error pattern ID")] = None,
    text: Annotated[str | None, Query(description="Free-text substring search across message")] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginatedLogEventsResponse:
    log_service = LogService(db)
    events, total = await log_service.search_events(
        user_id=current_user.id,
        project_id=id,
        service=service,
        level=level,
        start_time=start_time,
        end_time=end_time,
        pattern_id=pattern_id,
        query=text,
        limit=limit,
        offset=offset,
    )
    return PaginatedLogEventsResponse(
        items=[LogEventResponse.model_validate(e) for e in events],
        total=total,
        limit=limit,
        offset=offset,
    )
