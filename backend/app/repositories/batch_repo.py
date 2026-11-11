"""Repository for log batch metadata operations."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.log_batch import LogBatch


class BatchRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        project_id: uuid.UUID,
        source: str,
        filename: str | None = None,
        storage_path: str | None = None,
    ) -> LogBatch:
        batch = LogBatch(
            project_id=project_id,
            source=source,
            filename=filename,
            storage_path=storage_path,
            status="pending",
        )
        self.db.add(batch)
        await self.db.commit()
        await self.db.refresh(batch)
        return batch

    async def get_by_id(self, batch_id: uuid.UUID) -> LogBatch | None:
        result = await self.db.execute(select(LogBatch).where(LogBatch.id == batch_id))
        return result.scalar_one_or_none()

    async def get_by_id_and_project(
        self, batch_id: uuid.UUID, project_id: uuid.UUID
    ) -> LogBatch | None:
        stmt = select(LogBatch).where(
            LogBatch.id == batch_id,
            LogBatch.project_id == project_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_project(
        self, project_id: uuid.UUID, limit: int = 50, offset: int = 0
    ) -> list[LogBatch]:
        stmt = (
            select(LogBatch)
            .where(LogBatch.project_id == project_id)
            .order_by(LogBatch.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update_status(
        self,
        batch: LogBatch,
        status: str,
        line_count: int | None = None,
        error: str | None = None,
    ) -> LogBatch:
        batch.status = status
        if line_count is not None:
            batch.line_count = line_count
        if error is not None:
            batch.error = error
        await self.db.commit()
        await self.db.refresh(batch)
        return batch


class SyncBatchRepository:
    """Synchronous repository used inside Celery worker tasks."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, batch_id: uuid.UUID) -> LogBatch | None:
        return self.db.query(LogBatch).filter(LogBatch.id == batch_id).one_or_none()

    def update_status(
        self,
        batch: LogBatch,
        status: str,
        line_count: int | None = None,
        error: str | None = None,
    ) -> LogBatch:
        batch.status = status
        if line_count is not None:
            batch.line_count = line_count
        batch.error = error
        self.db.commit()
        self.db.refresh(batch)
        return batch
