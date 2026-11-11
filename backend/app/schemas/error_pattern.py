"""ErrorPattern API schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TrendBucket(BaseModel):
    bucket_start: str
    count: int


class ErrorPatternResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    fingerprint: str
    template: str
    level: str
    sample_service: str
    first_seen: datetime
    last_seen: datetime
    total_count: int
    example_event_ids: list[int] = []
    trend: list[TrendBucket] = []


class PaginatedPatternsResponse(BaseModel):
    items: list[ErrorPatternResponse]
    total: int
    limit: int
    offset: int
