"""IncidentReport database repository."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.incident_report import IncidentReport


class ReportRepository:
    """Database access operations for IncidentReports."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_latest_by_incident(
        self, incident_id: uuid.UUID
    ) -> IncidentReport | None:
        """Retrieve the latest version report for an incident."""
        stmt = (
            select(IncidentReport)
            .where(IncidentReport.incident_id == incident_id)
            .order_by(IncidentReport.version.desc(), IncidentReport.created_at.desc())
            .limit(1)
        )
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()

    async def get_next_version(self, incident_id: uuid.UUID) -> int:
        """Determine next sequential report version for an incident."""
        stmt = select(func.max(IncidentReport.version)).where(
            IncidentReport.incident_id == incident_id
        )
        res = await self.db.execute(stmt)
        max_ver = res.scalar_one()
        return (max_ver or 0) + 1

    async def create_pending_report(
        self, incident_id: uuid.UUID, version: int
    ) -> IncidentReport:
        """Insert a new pending report placeholder."""
        report = IncidentReport(
            id=uuid.uuid4(),
            incident_id=incident_id,
            version=version,
            status="pending",
            affected_services=[],
            suggested_fix=[],
            evidence={},
            validation_status="pending",
            created_at=datetime.now(UTC),
        )
        self.db.add(report)
        await self.db.commit()
        await self.db.refresh(report)
        return report
