"""User request and response schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class UserCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="User full name")
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., min_length=8, max_length=128, description="User password")

    @field_validator("email")
    @classmethod
    def normalise_email(cls, v: str) -> str:
        return v.strip().lower()


class UserLogin(BaseModel):
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., description="User password")

    @field_validator("email")
    @classmethod
    def normalise_email(cls, v: str) -> str:
        return v.strip().lower()


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
