"""API Key management endpoints scoped to authenticated projects."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.api_key import ApiKeyCreate, ApiKeyCreatedResponse, ApiKeyResponse
from app.services.api_key_service import ApiKeyService

router = APIRouter(prefix="/projects/{id}/api-keys", tags=["API Keys"])


@router.post(
    "",
    response_model=ApiKeyCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new ingestion API key (raw key shown once)",
)
async def create_api_key(
    id: uuid.UUID,
    data: ApiKeyCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApiKeyCreatedResponse:
    api_key_service = ApiKeyService(db)
    api_key, raw_key = await api_key_service.create_key(current_user.id, id, data)
    return ApiKeyCreatedResponse(
        id=api_key.id,
        raw_key=raw_key,
        key_prefix=api_key.key_prefix,
        label=api_key.label,
        created_at=api_key.created_at,
    )


@router.get(
    "",
    response_model=list[ApiKeyResponse],
    summary="List all API keys for an owned project (hashes only)",
)
async def list_api_keys(
    id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ApiKeyResponse]:
    api_key_service = ApiKeyService(db)
    keys = await api_key_service.list_keys(current_user.id, id)
    return [ApiKeyResponse.model_validate(k) for k in keys]


@router.delete(
    "/{key_id}",
    response_model=ApiKeyResponse,
    summary="Revoke an ingestion API key",
)
async def revoke_api_key(
    id: uuid.UUID,
    key_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApiKeyResponse:
    api_key_service = ApiKeyService(db)
    revoked = await api_key_service.revoke_key(current_user.id, id, key_id)
    return ApiKeyResponse.model_validate(revoked)
