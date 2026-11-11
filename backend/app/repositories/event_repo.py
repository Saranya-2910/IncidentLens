"""Repository for log event insertion and query filtering."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.log_event import LogEvent


class EventRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def search_events(
        self,
        project_id: uuid.UUID,
        service: str | None = None,
        level: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        pattern_id: uuid.UUID | None = None,
        query_text: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[LogEvent], int]:
        """Search and filter log events strictly scoped to project_id, returning (items, total_count)."""
        base_stmt = select(LogEvent).where(LogEvent.project_id == project_id)
        count_stmt = select(func.count(LogEvent.id)).where(LogEvent.project_id == project_id)

        if service:
            base_stmt = base_stmt.where(LogEvent.service == service)
            count_stmt = count_stmt.where(LogEvent.service == service)
        if level:
            base_stmt = base_stmt.where(LogEvent.level == level.upper())
            count_stmt = count_stmt.where(LogEvent.level == level.upper())
        if start_time:
            base_stmt = base_stmt.where(LogEvent.ts >= start_time)
            count_stmt = count_stmt.where(LogEvent.ts >= start_time)
        if end_time:
            base_stmt = base_stmt.where(LogEvent.ts <= end_time)
            count_stmt = count_stmt.where(LogEvent.ts <= end_time)
        if pattern_id:
            base_stmt = base_stmt.where(LogEvent.pattern_id == pattern_id)
            count_stmt = count_stmt.where(LogEvent.pattern_id == pattern_id)
        if query_text:
            base_stmt = base_stmt.where(LogEvent.message.ilike(f"%{query_text}%"))
            count_stmt = count_stmt.where(LogEvent.message.ilike(f"%{query_text}%"))

        # Execute total count
        count_result = await self.db.execute(count_stmt)
        total_count = count_result.scalar_one()

        # Execute paginated query ordered chronologically descending
        data_stmt = (
            base_stmt.order_by(LogEvent.ts.desc(), LogEvent.id.desc())
            .limit(limit)
            .offset(offset)
        )
        data_result = await self.db.execute(data_stmt)
        items = list(data_result.scalars().all())

        return items, total_count

    async def get_by_id(
        self, project_id: uuid.UUID, event_id: int
    ) -> LogEvent | None:
        """Fetch a single stored log event strictly scoped to project_id."""
        stmt = select(LogEvent).where(
            LogEvent.id == event_id,
            LogEvent.project_id == project_id,
        )
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()


class SyncEventRepository:
    """Synchronous repository used by Celery worker for fast bulk loading."""

    def __init__(self, db: Session):
        self.db = db

    def delete_by_batch_id(self, batch_id: uuid.UUID) -> int:
        """Delete all events associated with a batch ID to enable idempotent retries."""
        deleted = (
            self.db.query(LogEvent)
            .filter(LogEvent.batch_id == batch_id)
            .delete(synchronize_session=False)
        )
        self.db.commit()
        return deleted

    def bulk_insert(self, events: list[dict[str, Any]]) -> None:
        """Perform chunked bulk insertion for maximum ingestion speed."""
        if not events:
            return
        self.db.execute(insert(LogEvent), events)
        self.db.commit()
