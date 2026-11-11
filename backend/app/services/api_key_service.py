"""API Key management and ingestion authentication service."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, UnauthorizedError
from app.core.rate_limit import RateLimitExceededError, check_rate_limit
from app.core.security import generate_api_key, verify_api_key_hash
from app.models.api_key import ApiKey
from app.models.project import Project
from app.repositories.api_key_repo import ApiKeyRepository
from app.repositories.project_repo import ProjectRepository
from app.schemas.api_key import ApiKeyCreate


class ApiKeyService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.api_key_repo = ApiKeyRepository(db)
        self.project_repo = ProjectRepository(db)

    async def _verify_project_ownership(
        self, user_id: uuid.UUID, project_id: uuid.UUID
    ) -> Project:
        project = await self.project_repo.get_by_id_and_user(project_id, user_id)
        if not project:
            raise NotFoundError("Project not found")
        return project

    async def create_key(
        self, user_id: uuid.UUID, project_id: uuid.UUID, data: ApiKeyCreate
    ) -> tuple[ApiKey, str]:
        """Generate a new API key for an owned project. Returns created record and raw key."""
        await self._verify_project_ownership(user_id, project_id)
        raw_key, key_prefix, key_hash = generate_api_key()
        api_key = await self.api_key_repo.create(
            project_id=project_id,
            key_prefix=key_prefix,
            key_hash=key_hash,
            label=data.label,
        )
        return api_key, raw_key

    async def list_keys(
        self, user_id: uuid.UUID, project_id: uuid.UUID
    ) -> list[ApiKey]:
        """List all API keys for an owned project."""
        await self._verify_project_ownership(user_id, project_id)
        return await self.api_key_repo.list_by_project(project_id)

    async def revoke_key(
        self, user_id: uuid.UUID, project_id: uuid.UUID, key_id: uuid.UUID
    ) -> ApiKey:
        """Revoke an API key for an owned project."""
        await self._verify_project_ownership(user_id, project_id)
        api_key = await self.api_key_repo.get_by_id_and_project(key_id, project_id)
        if not api_key:
            raise NotFoundError("API key not found")
        return await self.api_key_repo.revoke(api_key)

    async def authenticate_key(self, raw_key: str) -> Project:
        """Authenticate an incoming raw API key for ingestion requests."""
        if not raw_key or not raw_key.startswith("il_live_"):
            raise UnauthorizedError("Invalid API key format")

        parts = raw_key.split("_")
        if len(parts) < 4:
            raise UnauthorizedError("Invalid API key format")

        key_prefix = f"{parts[0]}_{parts[1]}_{parts[2]}"

        # Rate limit per API key: max 120 ingestion requests per minute
        is_allowed = await check_rate_limit(
            key=f"rate_limit:ingest:{key_prefix}",
            max_requests=120,
            window_seconds=60,
        )
        if not is_allowed:
            raise RateLimitExceededError("Ingestion rate limit exceeded for this API key")

        candidates = await self.api_key_repo.find_by_prefix(key_prefix)
        matched_key: ApiKey | None = None

        for candidate in candidates:
            if verify_api_key_hash(raw_key, candidate.key_hash):
                matched_key = candidate
                break

        if not matched_key:
            raise UnauthorizedError("Invalid API key")

        if matched_key.revoked_at is not None:
            raise UnauthorizedError("API key has been revoked")

        # Update last used timestamp
        await self.api_key_repo.update_last_used(matched_key)

        # Retrieve associated project
        project = await self.project_repo.db.get(Project, matched_key.project_id)
        if not project:
            raise UnauthorizedError("Associated project not found")

        return project
