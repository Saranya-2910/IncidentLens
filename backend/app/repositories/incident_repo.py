"""Incident database repository."""

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.incident import Incident, IncidentPattern
from app.models.log_event import LogEvent


class IncidentRepository:
    """Handles CRUD, querying, and timeline generation for Incidents."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_by_project(
        self,
        project_id: uuid.UUID,
        status: str | None = None,
        severity: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Incident], int]:
        """List incidents for a project with optional filters and total count."""
        base_query = select(Incident).where(Incident.project_id == project_id)

        if status:
            base_query = base_query.where(Incident.status == status.lower())
        if severity:
            base_query = base_query.where(Incident.severity == severity.lower())

        count_stmt = select(func.count()).select_from(base_query.subquery())
        total_res = await self.db.execute(count_stmt)
        total = total_res.scalar_one()

        query = (
            base_query.options(selectinload(Incident.origin_pattern))
            .order_by(Incident.started_at.desc())
            .limit(limit)
            .offset(offset)
        )
        res = await self.db.execute(query)
        incidents = list(res.scalars().all())
        return incidents, total

    async def get_by_id(
        self, incident_id: uuid.UUID, project_id: uuid.UUID
    ) -> Incident | None:
        """Get incident by ID within a project, loading origin pattern and associations."""
        stmt = (
            select(Incident)
            .where(Incident.id == incident_id, Incident.project_id == project_id)
            .options(
                selectinload(Incident.origin_pattern),
                selectinload(Incident.pattern_associations).selectinload(IncidentPattern.pattern),
            )
        )
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()

    async def get_incident_timeline(
        self, incident: Incident
    ) -> list[dict[str, Any]]:
        """Generate timeline of events grouped by time, service, and pattern."""
        # Query events occurring during the incident window for this project
        stmt = (
            select(
                LogEvent.id,
                LogEvent.ts,
                LogEvent.service,
                LogEvent.level,
                LogEvent.pattern_id,
                LogEvent.message,
            )
            .where(
                LogEvent.project_id == incident.project_id,
                LogEvent.ts >= incident.started_at,
                LogEvent.ts <= (incident.ended_at or incident.started_at),
                LogEvent.level.in_(["ERROR", "FATAL", "CRITICAL", "WARN"]),
            )
            .order_by(LogEvent.ts.asc())
        )
        res = await self.db.execute(stmt)
        events = res.all()

        timeline_items = []
        for evt in events:
            timeline_items.append({
                "event_id": evt.id,
                "timestamp": evt.ts.isoformat(),
                "service": evt.service,
                "level": evt.level,
                "pattern_id": evt.pattern_id,
                "message": evt.message,
            })
        return timeline_items
