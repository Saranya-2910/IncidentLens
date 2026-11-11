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
            "resolution_note": incident.resolution_note,
            "resolved_at": incident.resolved_at,
            "created_at": incident.created_at,
            "patterns": patterns_list,
            "timeline": timeline,
        }

    async def _get_owned_incident(
        self, user_id: uuid.UUID, incident_id: uuid.UUID
    ) -> Incident:
        from sqlalchemy import select
        stmt = select(Incident.project_id).where(Incident.id == incident_id)
        res = await self.db.execute(stmt)
        project_id = res.scalar_one_or_none()
        if not project_id:
            raise NotFoundError("Incident not found")

        await self._verify_project_ownership(user_id, project_id)
        incident = await self.incident_repo.get_by_id(incident_id, project_id)
        if not incident:
            raise NotFoundError("Incident not found")
        return incident

    async def get_incident_by_id_only(
        self,
        user_id: uuid.UUID,
        incident_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Retrieve incident by ID verifying user owns the incident's project."""
        incident = await self._get_owned_incident(user_id, incident_id)
        return await self.get_incident_detail(user_id, incident.project_id, incident.id)

    async def resolve_incident(
        self,
        user_id: uuid.UUID,
        incident_id: uuid.UUID,
        status: str = "resolved",
        resolution_note: str | None = None,
    ) -> Incident:
        """Resolve or update resolution note for an owned incident."""
        incident = await self._get_owned_incident(user_id, incident_id)
        return await self.incident_repo.resolve_incident(
            incident=incident,
            status=status,
            resolution_note=resolution_note,
        )

    async def get_similar_incidents(
        self,
        user_id: uuid.UUID,
        incident_id: uuid.UUID,
        limit: int = 5,
        min_similarity: float | None = None,
    ) -> list[dict[str, Any]]:
        """Find semantically similar past incidents strictly scoped to the same project."""
        incident = await self._get_owned_incident(user_id, incident_id)
        return await self.incident_repo.find_similar_incidents(
            target_incident=incident,
            limit=limit,
            min_similarity=min_similarity,
        )

    async def get_project_stats(
        self,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Compute project summary metrics: error rate series, top patterns, incident counts."""
        await self._verify_project_ownership(user_id, project_id)

        from datetime import UTC, datetime

        from sqlalchemy import func, select

        from app.models.error_pattern import ErrorPattern
        from app.models.log_event import LogEvent

        # 1. Event counts
        tot_ev_res = await self.db.execute(
            select(func.count(LogEvent.id)).where(LogEvent.project_id == project_id)
        )
        total_events = tot_ev_res.scalar_one()

        err_ev_res = await self.db.execute(
            select(func.count(LogEvent.id)).where(
                LogEvent.project_id == project_id,
                LogEvent.level.in_(["ERROR", "FATAL", "CRITICAL"]),
            )
        )
        error_events = err_ev_res.scalar_one()

        # 2. Pattern count & top 5 error patterns
        tot_pat_res = await self.db.execute(
            select(func.count(ErrorPattern.id)).where(ErrorPattern.project_id == project_id)
        )
        total_patterns = tot_pat_res.scalar_one()

        top_pat_res = await self.db.execute(
            select(ErrorPattern)
            .where(ErrorPattern.project_id == project_id)
            .order_by(ErrorPattern.total_count.desc())
            .limit(5)
        )
        top_patterns = [
            {
                "id": p.id,
                "template": p.template,
                "level": p.level,
                "sample_service": p.sample_service,
                "total_count": p.total_count,
            }
            for p in top_pat_res.scalars().all()
        ]

        # 3. Incident counts
        open_inc_res = await self.db.execute(
            select(func.count(Incident.id)).where(
                Incident.project_id == project_id, Incident.status == "open"
            )
        )
        open_incidents = open_inc_res.scalar_one()

        res_inc_res = await self.db.execute(
            select(func.count(Incident.id)).where(
                Incident.project_id == project_id, Incident.status == "resolved"
            )
        )
        resolved_incidents = res_inc_res.scalar_one()

        # 4. Error rate series (1-minute buckets across recent events)
        ev_series_stmt = (
            select(LogEvent.ts, LogEvent.level)
            .where(LogEvent.project_id == project_id)
            .order_by(LogEvent.ts.asc())
            .limit(10000)
        )
        ev_rows = (await self.db.execute(ev_series_stmt)).all()
        buckets: dict[int, dict[str, int]] = {}
        for ts, lvl in ev_rows:
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            epoch = int(ts.timestamp())
            b_key = (epoch // 60) * 60
            if b_key not in buckets:
                buckets[b_key] = {"total": 0, "error": 0}
            buckets[b_key]["total"] += 1
            if lvl in ("ERROR", "FATAL", "CRITICAL"):
                buckets[b_key]["error"] += 1

        error_rate_series = [
            {
                "bucket": datetime.fromtimestamp(b_epoch, tz=UTC).isoformat(),
                "total_events": counts["total"],
                "error_events": counts["error"],
            }
            for b_epoch, counts in sorted(buckets.items())
        ]

        return {
            "project_id": project_id,
            "total_events": total_events,
            "error_events": error_events,
            "total_patterns": total_patterns,
            "total_incidents": open_incidents + resolved_incidents,
            "open_incidents": open_incidents,
            "resolved_incidents": resolved_incidents,
            "error_rate_series": error_rate_series,
            "top_patterns": top_patterns,
        }
