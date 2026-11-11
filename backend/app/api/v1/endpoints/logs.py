"""Log upload, batch status, and event search endpoints."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.demo import DemoScenarioItem, LoadDemoDataRequest, LoadDemoDataResponse
from app.schemas.log_batch import BatchUploadResponse, LogBatchResponse
from app.schemas.log_event import (
    LogEventResponse,
    PaginatedLogEventsResponse,
    RetentionCleanupResponse,
)
from app.services.log_service import LogService

router = APIRouter(tags=["Logs & Ingestion"])


@router.get(
    "/projects/demo-scenarios",
    response_model=list[DemoScenarioItem],
    summary="List all available simulated demo scenarios",
)
async def list_demo_scenarios(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[DemoScenarioItem]:
    log_service = LogService(db)
    scenarios = log_service.list_demo_scenarios()
    return [DemoScenarioItem.model_validate(s) for s in scenarios]


@router.post(
    "/projects/{id}/demo-data",
    response_model=LoadDemoDataResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Seed an owned project with a simulated scenario dataset",
)
async def load_demo_data(
    id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    payload: LoadDemoDataRequest | None = None,
) -> LoadDemoDataResponse:
    log_service = LogService(db)
    scenario_id = payload.scenario_id if payload else None
    batch, target_scenario, total_lines = await log_service.load_demo_data(
        current_user.id, id, scenario_id=scenario_id
    )
    return LoadDemoDataResponse(
        batch_id=batch.id,
        scenario_id=target_scenario,
        status=batch.status,
        total_lines=total_lines,
        message="Demo incident dataset queued for background ingestion",
    )


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


@router.get(
    "/projects/{id}/events/{event_id}",
    response_model=LogEventResponse,
    summary="Retrieve full stored details of a single log event by ID",
)
async def get_project_event_detail(
    id: uuid.UUID,
    event_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LogEventResponse:
    log_service = LogService(db)
    event = await log_service.get_event_by_id(current_user.id, id, event_id)
    return LogEventResponse.model_validate(event)


@router.post(
    "/projects/{id}/events/retention-cleanup",
    response_model=RetentionCleanupResponse,
    summary="Purge old log events exceeding the configured retention window",
)
async def purge_expired_events(
    id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    retention_days: Annotated[int | None, Query(ge=1, le=3650)] = None,
) -> RetentionCleanupResponse:
    log_service = LogService(db)
    res = await log_service.purge_expired_events(
        current_user.id, id, retention_days=retention_days
    )
    return RetentionCleanupResponse.model_validate(res)
