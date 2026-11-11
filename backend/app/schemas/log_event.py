"""Log event schemas."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LogEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: uuid.UUID
    batch_id: uuid.UUID
    ts: datetime
    service: str
    level: str
    message: str
    trace_id: str | None
    pattern_id: uuid.UUID | None
    attributes: dict[str, Any]
    raw_line: str


class PaginatedLogEventsResponse(BaseModel):
    items: list[LogEventResponse]
    total: int
    limit: int = Field(50, ge=1, le=1000)
    offset: int = Field(0, ge=0)
