"""ErrorPattern business logic service."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.repositories.pattern_repo import PatternRepository
from app.repositories.project_repo import ProjectRepository


class PatternService:
    """Manages pattern querying, tenant isolation, and trend aggregation."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.project_repo = ProjectRepository(db)
        self.pattern_repo = PatternRepository(db)

    async def _verify_project_ownership(self, user_id: uuid.UUID, project_id: uuid.UUID) -> None:
        project = await self.project_repo.get_by_id_and_user(project_id, user_id)
        if not project:
            raise NotFoundError("Project not found")

    async def list_patterns(
        self,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        level: str | None = None,
        service: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        include_samples: bool = True,
        include_trend: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """List patterns for an owned project, augmenting with sample events and trend buckets."""
        await self._verify_project_ownership(user_id, project_id)

        patterns, total = await self.pattern_repo.list_by_project(
            project_id=project_id,
            level=level,
            service=service,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset,
        )

        results: list[dict[str, Any]] = []
        for p in patterns:
            pattern_dict: dict[str, Any] = {
                "id": p.id,
                "project_id": p.project_id,
                "fingerprint": p.fingerprint,
                "template": p.template,
                "level": p.level,
                "sample_service": p.sample_service,
                "first_seen": p.first_seen,
                "last_seen": p.last_seen,
                "total_count": p.total_count,
                "example_event_ids": [],
                "trend": [],
            }

            if include_samples:
                samples = await self.pattern_repo.get_example_event_ids(p.id, limit=3)
                pattern_dict["example_event_ids"] = samples

            if include_trend:
                trend = await self.pattern_repo.get_trend_buckets(p.id, bucket_seconds=3600)
                pattern_dict["trend"] = trend

            results.append(pattern_dict)

        return results, total

    async def get_pattern_detail(
        self,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        pattern_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Retrieve single pattern with detailed trend and sample event IDs."""
        await self._verify_project_ownership(user_id, project_id)

        pattern = await self.pattern_repo.get_by_id(pattern_id, project_id)
        if not pattern:
            raise NotFoundError("Error pattern not found")

        samples = await self.pattern_repo.get_example_event_ids(pattern.id, limit=5)
        trend = await self.pattern_repo.get_trend_buckets(pattern.id, bucket_seconds=600)

        return {
            "id": pattern.id,
            "project_id": pattern.project_id,
            "fingerprint": pattern.fingerprint,
            "template": pattern.template,
            "level": pattern.level,
            "sample_service": pattern.sample_service,
            "first_seen": pattern.first_seen,
            "last_seen": pattern.last_seen,
            "total_count": pattern.total_count,
            "example_event_ids": samples,
            "trend": trend,
        }
