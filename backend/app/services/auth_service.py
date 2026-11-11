"""Authentication and account service."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, UnauthorizedError
from app.core.rate_limit import RateLimitExceededError, check_rate_limit
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.schemas.user import UserCreate, UserLogin


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_repo = UserRepository(db)

    async def register(self, data: UserCreate) -> tuple[User, str]:
        """Register a new user, returning the created user and JWT access token."""
        existing = await self.user_repo.get_by_email(data.email)
        if existing:
            raise ConflictError("An account with this email address already exists")

        pwd_hash = hash_password(data.password)
        user = await self.user_repo.create(
            name=data.name,
            email=data.email,
            password_hash=pwd_hash,
        )
        token = create_access_token(subject=str(user.id))
        return user, token

    async def login(self, data: UserLogin, client_ip: str) -> tuple[User, str]:
        """Authenticate user credentials with rate-limiting protection."""
        # Rate limit login attempts per IP: max 5 requests per 60 seconds
        is_allowed = await check_rate_limit(
            key=f"rate_limit:login:{client_ip}",
            max_requests=5,
            window_seconds=60,
        )
        if not is_allowed:
            raise RateLimitExceededError(
                "Too many login attempts. Please wait a minute and try again."
            )

        user = await self.user_repo.get_by_email(data.email)
        if not user or not verify_password(data.password, user.password_hash):
            raise UnauthorizedError("Invalid email or password")

        token = create_access_token(subject=str(user.id))
        return user, token
