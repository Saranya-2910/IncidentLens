"""ErrorPattern database repository."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.error_pattern import ErrorPattern
from app.models.log_event import LogEvent


class PatternRepository:
    """Handles CRUD, filtering, and trend queries for ErrorPatterns."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_by_project(
        self,
        project_id: uuid.UUID,
        level: str | None = None,
        service: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ErrorPattern], int]:
        """List patterns for a project with optional filters and total count."""
        base_query = select(ErrorPattern).where(ErrorPattern.project_id == project_id)

        if level:
            base_query = base_query.where(ErrorPattern.level == level.upper())
        if service:
            base_query = base_query.where(ErrorPattern.sample_service == service)
        if start_time:
            base_query = base_query.where(ErrorPattern.last_seen >= start_time)
        if end_time:
            base_query = base_query.where(ErrorPattern.first_seen <= end_time)

        # Count total matches
        count_stmt = select(func.count()).select_from(base_query.subquery())
        total_res = await self.db.execute(count_stmt)
        total = total_res.scalar_one()

        # Paginate ordered by total_count descending, then last_seen descending
        query = (
            base_query.order_by(ErrorPattern.total_count.desc(), ErrorPattern.last_seen.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(query)
        patterns = list(result.scalars().all())
        return patterns, total

    async def get_by_id(
        self, pattern_id: uuid.UUID, project_id: uuid.UUID
    ) -> ErrorPattern | None:
        """Get a single pattern by ID within a project."""
        stmt = select(ErrorPattern).where(
            ErrorPattern.id == pattern_id,
            ErrorPattern.project_id == project_id,
        )
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()

    async def get_example_event_ids(
        self, pattern_id: uuid.UUID, limit: int = 5
    ) -> list[int]:
        """Fetch up to N sample event IDs belonging to a pattern."""
        stmt = (
            select(LogEvent.id)
            .where(LogEvent.pattern_id == pattern_id)
            .order_by(LogEvent.ts.desc())
            .limit(limit)
        )
        res = await self.db.execute(stmt)
        return list(res.scalars().all())

    async def get_trend_buckets(
        self,
        pattern_id: uuid.UUID,
        bucket_seconds: int = 3600,
    ) -> list[dict[str, Any]]:
        """Calculate frequency trend over time buckets for a given pattern."""
        # Query event timestamps for the pattern
        stmt = (
            select(LogEvent.ts)
            .where(LogEvent.pattern_id == pattern_id)
            .order_by(LogEvent.ts.asc())
        )
        res = await self.db.execute(stmt)
        timestamps = list(res.scalars().all())
        if not timestamps:
            return []

        # Bucket timestamps in Python for SQLite and PostgreSQL compatibility
        buckets: dict[int, int] = {}
        for ts in timestamps:
            epoch = int(ts.timestamp())
            bucket_key = (epoch // bucket_seconds) * bucket_seconds
            buckets[bucket_key] = buckets.get(bucket_key, 0) + 1

        trend_data = []
        for b_epoch in sorted(buckets.keys()):
            b_dt = datetime.fromtimestamp(b_epoch, tz=UTC)
            trend_data.append({
                "bucket_start": b_dt.isoformat(),
                "count": buckets[b_epoch],
            })
        return trend_data
