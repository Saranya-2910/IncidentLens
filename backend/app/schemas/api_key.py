"""API Key request and response schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ApiKeyCreate(BaseModel):
    label: str = Field(..., min_length=1, max_length=255, description="Descriptive label for API key")


class ApiKeyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key_prefix: str
    label: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class ApiKeyCreatedResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    raw_key: str = Field(..., description="Raw API key string shown only once upon creation")
    key_prefix: str
    label: str
    created_at: datetime
