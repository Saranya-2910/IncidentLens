"""Incident API request and response schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class OriginCandidate(BaseModel):
    pattern_id: uuid.UUID
    score: float
    service: str
    template: str
    level: str
    count: int
    first_seen: str
    reason: str


class IncidentPatternItem(BaseModel):
    pattern_id: uuid.UUID
    count: int
    first_seen: str
    template: str | None = None
    level: str | None = None
    sample_service: str | None = None


class TimelineItem(BaseModel):
    event_id: int
    timestamp: str
    service: str
    level: str
    pattern_id: uuid.UUID | None = None
    message: str


class IncidentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    status: str
    severity: str
    started_at: datetime
    ended_at: datetime | None
    origin_pattern_id: uuid.UUID | None
    origin_pattern_template: str | None = None
    affected_services: list[str]
    event_count: int
    created_at: datetime


class IncidentDetailResponse(IncidentResponse):
    origin_candidates: list[OriginCandidate] = []
    patterns: list[IncidentPatternItem] = []
    timeline: list[TimelineItem] = []


class PaginatedIncidentsResponse(BaseModel):
    items: list[IncidentResponse]
    total: int
    limit: int
    offset: int
