"""Incident report generation and retrieval business logic service."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models.incident import Incident
from app.models.incident_report import IncidentReport
from app.repositories.project_repo import ProjectRepository
from app.repositories.report_repo import ReportRepository
from app.workers.celery_app import dispatch_background_task
from app.workers.tasks import explain_incident_task


class ReportService:
    """Manages idempotent LLM report generation, status retrieval, and tenant isolation."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.project_repo = ProjectRepository(db)
        self.report_repo = ReportRepository(db)

    async def _verify_incident_ownership(
        self, user_id: uuid.UUID, incident_id: uuid.UUID
    ) -> Incident:
        """Fetch incident ensuring its parent project belongs to current user."""
        stmt = select(Incident).where(Incident.id == incident_id)
        res = await self.db.execute(stmt)
        incident = res.scalar_one_or_none()
        if not incident:
            raise NotFoundError("Incident not found")

        project = await self.project_repo.get_by_id_and_user(incident.project_id, user_id)
        if not project:
            raise NotFoundError("Incident not found")

        return incident

    async def trigger_explanation(
        self, user_id: uuid.UUID, incident_id: uuid.UUID, force: bool = False
    ) -> IncidentReport:
        """Idempotently trigger AI explanation generation in background."""
        await self._verify_incident_ownership(user_id, incident_id)

        latest = await self.report_repo.get_latest_by_incident(incident_id)
        if not force and latest and latest.status in ("pending", "processing", "done"):
            return latest

        next_version = await self.report_repo.get_next_version(incident_id)
        report = await self.report_repo.create_pending_report(incident_id, version=next_version)

        dispatch_background_task(explain_incident_task, str(report.id))
        await self.db.refresh(report)
        return report

    async def get_latest_report(
        self, user_id: uuid.UUID, incident_id: uuid.UUID
    ) -> IncidentReport | None:
        """Fetch the latest report for an owned incident."""
        await self._verify_incident_ownership(user_id, incident_id)
        return await self.report_repo.get_latest_by_incident(incident_id)
