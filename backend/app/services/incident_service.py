"""Incident business logic service."""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models.incident import Incident
from app.repositories.incident_repo import IncidentRepository
from app.repositories.project_repo import ProjectRepository


class IncidentService:
    """Manages incident querying, detail view with timelines, and tenant isolation."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.project_repo = ProjectRepository(db)
        self.incident_repo = IncidentRepository(db)

    async def _verify_project_ownership(self, user_id: uuid.UUID, project_id: uuid.UUID) -> None:
        project = await self.project_repo.get_by_id_and_user(project_id, user_id)
        if not project:
            raise NotFoundError("Project not found")

    async def list_incidents(
        self,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        status: str | None = None,
        severity: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Incident], int]:
        """List incidents for an owned project."""
        await self._verify_project_ownership(user_id, project_id)
        return await self.incident_repo.list_by_project(
            project_id=project_id,
            status=status,
            severity=severity,
            limit=limit,
            offset=offset,
        )

    async def get_incident_detail(
        self,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        incident_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Retrieve full incident detail including timeline and associated error patterns."""
        await self._verify_project_ownership(user_id, project_id)

        incident = await self.incident_repo.get_by_id(incident_id, project_id)
        if not incident:
            raise NotFoundError("Incident not found")

        timeline = await self.incident_repo.get_incident_timeline(incident)

        patterns_list = []
        for assoc in incident.pattern_associations:
            patterns_list.append({
                "pattern_id": assoc.pattern_id,
                "count": assoc.count,
                "first_seen": assoc.first_seen_in_incident.isoformat(),
                "template": assoc.pattern.template if assoc.pattern else None,
                "level": assoc.pattern.level if assoc.pattern else None,
                "sample_service": assoc.pattern.sample_service if assoc.pattern else None,
            })

        return {
            "id": incident.id,
            "project_id": incident.project_id,
            "status": incident.status,
            "severity": incident.severity,
            "started_at": incident.started_at,
            "ended_at": incident.ended_at,
            "origin_pattern_id": incident.origin_pattern_id,
            "origin_pattern_template": incident.origin_pattern.template if incident.origin_pattern else None,
            "affected_services": incident.affected_services,
            "origin_candidates": incident.origin_candidates,
            "event_count": incident.event_count,
            "created_at": incident.created_at,
            "patterns": patterns_list,
            "timeline": timeline,
        }

    async def get_incident_by_id_only(
        self,
        user_id: uuid.UUID,
        incident_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Retrieve incident by ID verifying user owns the incident's project."""
        # Find project first by querying incident
        from sqlalchemy import select
        stmt = select(Incident.project_id).where(Incident.id == incident_id)
        res = await self.db.execute(stmt)
        project_id = res.scalar_one_or_none()
        if not project_id:
            raise NotFoundError("Incident not found")

        return await self.get_incident_detail(user_id, project_id, incident_id)
