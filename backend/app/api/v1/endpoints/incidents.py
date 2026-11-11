"""Incident list, detail, and timeline endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.incident import (
    IncidentDetailResponse,
    IncidentResponse,
    PaginatedIncidentsResponse,
    ProjectStatsResponse,
    ResolveIncidentRequest,
    SimilarIncidentMatch,
    SimilarIncidentsResponse,
)
from app.schemas.incident_report import (
    AI_DISCLAIMER,
    EvidenceLineResponse,
    ExplainTriggerRequest,
    ExplainTriggerResponse,
    IncidentReportResponse,
    VerifiedClaimResponse,
)
from app.services.incident_service import IncidentService
from app.services.report_service import ReportService

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


@router.post(
    "/incidents/{id}/explain",
    response_model=ExplainTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Idempotently trigger AI root-cause report generation for an incident",
)
async def explain_incident(
    id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    payload: ExplainTriggerRequest | None = None,
) -> ExplainTriggerResponse:
    report_service = ReportService(db)
    force = payload.force if payload else False
    report = await report_service.trigger_explanation(current_user.id, id, force=force)
    return ExplainTriggerResponse(
        report_id=report.id,
        incident_id=report.incident_id,
        version=report.version,
        status=report.status,
        message=(
            "Report generation queued in background"
            if report.status in ("pending", "processing")
            else "Existing report returned (use force=true to regenerate)"
        ),
    )


@router.get(
    "/incidents/{id}/report",
    response_model=IncidentReportResponse,
    summary="Retrieve the latest AI root-cause report with verified evidence citations",
)
async def get_incident_report(
    id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> IncidentReportResponse:
    report_service = ReportService(db)
    report = await report_service.get_latest_report(current_user.id, id)

    if not report:
        return IncidentReportResponse(
            incident_id=id,
            status="not_generated",
            validation_status="not_generated",
            disclaimer=AI_DISCLAIMER,
        )

    ev_dict = report.evidence or {}
    claims = [
        VerifiedClaimResponse.model_validate(c) for c in ev_dict.get("claims", [])
    ]
    evidence_lines = [
        EvidenceLineResponse.model_validate(line)
        for line in ev_dict.get("evidence_lines", [])
    ]

    return IncidentReportResponse(
        id=report.id,
        incident_id=report.incident_id,
        version=report.version,
        status=report.status,
        summary=report.summary,
        root_cause=report.root_cause,
        confidence=report.confidence,
        severity=report.severity,
        affected_services=report.affected_services,
        suggested_fixes=report.suggested_fix,
        claims=claims,
        evidence_lines=evidence_lines,
        validation_status=report.validation_status,
        unsupported_claim_count=report.unsupported_claim_count,
        model_name=report.model_name,
        prompt_version=report.prompt_version,
        input_tokens=report.input_tokens,
        output_tokens=report.output_tokens,
        total_incident_events=report.total_incident_events,
        selected_evidence_lines=report.selected_evidence_lines,
        error=report.error,
        created_at=report.created_at,
        disclaimer=AI_DISCLAIMER,
    )


@router.get(
    "/incidents/{id}/similar",
    response_model=SimilarIncidentsResponse,
    summary="Find semantically similar past incidents in the same project",
)
async def get_similar_incidents(
    id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
    min_similarity: Annotated[float | None, Query(ge=0.0, le=1.0)] = None,
) -> SimilarIncidentsResponse:
    incident_service = IncidentService(db)
    matches = await incident_service.get_similar_incidents(
        user_id=current_user.id,
        incident_id=id,
        limit=limit,
        min_similarity=min_similarity,
    )
    return SimilarIncidentsResponse(
        incident_id=id,
        items=[SimilarIncidentMatch.model_validate(m) for m in matches],
    )


@router.post(
    "/incidents/{id}/resolve",
    response_model=IncidentResponse,
    summary="Mark an incident as resolved and save a resolution note",
)
async def resolve_incident_post(
    id: uuid.UUID,
    payload: ResolveIncidentRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> IncidentResponse:
    incident_service = IncidentService(db)
    incident = await incident_service.resolve_incident(
        user_id=current_user.id,
        incident_id=id,
        status=payload.status,
        resolution_note=payload.resolution_note,
    )
    return IncidentResponse.model_validate(incident)


@router.patch(
    "/incidents/{id}",
    response_model=IncidentResponse,
    summary="Update incident status or resolution note",
)
async def update_incident_patch(
    id: uuid.UUID,
    payload: ResolveIncidentRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> IncidentResponse:
    incident_service = IncidentService(db)
    incident = await incident_service.resolve_incident(
        user_id=current_user.id,
        incident_id=id,
        status=payload.status,
        resolution_note=payload.resolution_note,
    )
    return IncidentResponse.model_validate(incident)


@router.get(
    "/projects/{id}/stats",
    response_model=ProjectStatsResponse,
    summary="Retrieve project error rate series, top error patterns, and incident counts",
)
async def get_project_stats(
    id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProjectStatsResponse:
    incident_service = IncidentService(db)
    stats = await incident_service.get_project_stats(current_user.id, id)
    return ProjectStatsResponse.model_validate(stats)
