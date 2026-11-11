"""Log batch schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class LogBatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    source: str
    filename: str | None
    status: str
    line_count: int
    error: str | None
    created_at: datetime


class BatchUploadResponse(BaseModel):
    batch_id: uuid.UUID
    status: str
    message: str = "Log batch accepted for background processing"
