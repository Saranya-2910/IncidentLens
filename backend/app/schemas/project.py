"""Project request and response schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Project name")
    description: str | None = Field(default=None, max_length=2000, description="Project description")


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime
