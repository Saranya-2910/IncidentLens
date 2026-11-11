"""Authentication and session endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.rate_limit import get_client_ip
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import TokenResponse, UserCreate, UserLogin, UserResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _set_auth_cookie(response: Response, token: str) -> None:
    """Set secure HttpOnly cookie for session."""
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=settings.ENVIRONMENT == "production",
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
async def register(
    data: UserCreate,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    auth_service = AuthService(db)
    user, token = await auth_service.register(data)
    _set_auth_cookie(response, token)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate and receive session token",
)
async def login(
    data: UserLogin,
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    client_ip = get_client_ip(request)
    auth_service = AuthService(db)
    user, token = await auth_service.login(data, client_ip=client_ip)
    _set_auth_cookie(response, token)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
    )


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="Log out and clear session cookie",
)
async def logout(response: Response) -> dict[str, str]:
    response.delete_cookie(
        key="access_token",
        httponly=True,
        secure=settings.ENVIRONMENT == "production",
        samesite="lax",
    )
    return {"message": "Logged out successfully"}


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Retrieve current authenticated user profile",
)
async def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    return UserResponse.model_validate(current_user)
