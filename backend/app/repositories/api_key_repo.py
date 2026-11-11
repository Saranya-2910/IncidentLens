"""API Key repository ensuring all operations are scoped to a verified project."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_key import ApiKey


class ApiKeyRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id_and_project(
        self, key_id: uuid.UUID, project_id: uuid.UUID
    ) -> ApiKey | None:
        """Fetch API key strictly checking both key ID and project ID."""
        stmt = select(ApiKey).where(
            ApiKey.id == key_id,
            ApiKey.project_id == project_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_project(self, project_id: uuid.UUID) -> list[ApiKey]:
        """List all API keys for a project."""
        stmt = (
            select(ApiKey)
            .where(ApiKey.project_id == project_id)
            .order_by(ApiKey.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def create(
        self,
        project_id: uuid.UUID,
        key_prefix: str,
        key_hash: str,
        label: str,
    ) -> ApiKey:
        """Create a new API key record storing only the prefix and SHA-256 hash."""
        api_key = ApiKey(
            project_id=project_id,
            key_prefix=key_prefix,
            key_hash=key_hash,
            label=label,
        )
        self.db.add(api_key)
        await self.db.commit()
        await self.db.refresh(api_key)
        return api_key

    async def revoke(self, api_key: ApiKey) -> ApiKey:
        """Revoke an API key by setting revoked_at timestamp."""
        api_key.revoked_at = datetime.now(UTC)
        await self.db.commit()
        await self.db.refresh(api_key)
        return api_key

    async def find_by_prefix(self, key_prefix: str) -> list[ApiKey]:
        """Find API keys matching prefix for ingestion authentication."""
        stmt = select(ApiKey).where(ApiKey.key_prefix == key_prefix)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update_last_used(self, api_key: ApiKey) -> None:
        """Update last_used_at timestamp when an ingestion key is used."""
        api_key.last_used_at = datetime.now(UTC)
        await self.db.commit()
