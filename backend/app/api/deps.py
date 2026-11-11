"""FastAPI dependencies for authentication and authorization."""

import uuid
from typing import Annotated

from fastapi import Cookie, Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import UnauthorizedError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.project import Project
from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.services.api_key_service import ApiKeyService

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    db: Annotated[AsyncSession, Depends(get_db)],
    bearer: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
    access_token_cookie: Annotated[str | None, Cookie(alias="access_token")] = None,
) -> User:
    """Extract and validate the current authenticated user from Bearer header or HttpOnly cookie."""
    token: str | None = None
    if bearer and bearer.credentials:
        token = bearer.credentials
    elif access_token_cookie:
        token = access_token_cookie

    if not token:
        raise UnauthorizedError("Authentication credentials were not provided")

    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        raise UnauthorizedError("Invalid or expired authentication token")

    try:
        user_id = uuid.UUID(payload["sub"])
    except (ValueError, TypeError) as err:
        raise UnauthorizedError("Malformed authentication token subject") from err

    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)
    if not user:
        raise UnauthorizedError("User account no longer exists")

    return user


async def get_api_key_project(
    db: Annotated[AsyncSession, Depends(get_db)],
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> Project:
    """Dependency verifying X-API-Key header for log ingestion, returning the verified Project."""
    if not x_api_key:
        raise UnauthorizedError("Missing X-API-Key header")

    api_key_service = ApiKeyService(db)
    return await api_key_service.authenticate_key(x_api_key)
