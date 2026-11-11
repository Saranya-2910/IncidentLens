"""Incident database repository."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai.embeddings import (
    build_report_embedding_text,
    cosine_similarity,
    get_embedding_client,
)
from app.core.config import settings
from app.models.error_pattern import ErrorPattern
from app.models.incident import Incident, IncidentPattern
from app.models.incident_report import IncidentReport
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

    async def resolve_incident(
        self,
        incident: Incident,
        status: str = "resolved",
        resolution_note: str | None = None,
    ) -> Incident:
        """Update incident resolution status and resolution note."""
        incident.status = status
        if resolution_note is not None:
            incident.resolution_note = resolution_note
        if status == "resolved":
            incident.resolved_at = datetime.now(UTC)
        else:
            incident.resolved_at = None

        await self.db.commit()
        await self.db.refresh(incident)
        return incident

    async def find_similar_incidents(
        self,
        target_incident: Incident,
        limit: int = 5,
        min_similarity: float | None = None,
    ) -> list[dict[str, Any]]:
        """Find past incidents in the same project matching the target incident's semantic vector."""
        threshold = min_similarity if min_similarity is not None else settings.SIMILARITY_THRESHOLD

        # 1. Obtain query embedding vector: prefer latest completed report embedding
        rep_stmt = (
            select(IncidentReport)
            .where(
                IncidentReport.incident_id == target_incident.id,
                IncidentReport.status == "done",
                IncidentReport.embedding.is_not(None),
            )
            .order_by(IncidentReport.version.desc())
            .limit(1)
        )
        rep_res = await self.db.execute(rep_stmt)
        target_report = rep_res.scalar_one_or_none()

        query_vector: list[float] | None = None
        if target_report and target_report.embedding is not None:
            query_vector = list(target_report.embedding)
        else:
            # Synthesize temporary embedding from incident patterns if report not yet generated
            pat_stmt = (
                select(ErrorPattern.template)
                .join(IncidentPattern, ErrorPattern.id == IncidentPattern.pattern_id)
                .where(IncidentPattern.incident_id == target_incident.id)
            )
            pat_res = await self.db.execute(pat_stmt)
            templates = list(pat_res.scalars().all())
            if templates:
                emb_text = build_report_embedding_text(
                    summary=None,
                    root_cause=None,
                    patterns=templates,
                )
                emb_client = get_embedding_client()
                query_vector = emb_client.embed(emb_text)

        if not query_vector:
            return []

        # 2. Query candidates strictly scoped to the same project
        conn = await self.db.connection()
        dialect_name = conn.dialect.name

        scored_matches: dict[uuid.UUID, dict[str, Any]] = {}

        if dialect_name == "postgresql":
            dist_expr = IncidentReport.embedding.cosine_distance(query_vector)
            pg_stmt = (
                select(Incident, IncidentReport, (1.0 - dist_expr).label("similarity"))
                .join(IncidentReport, Incident.id == IncidentReport.incident_id)
                .where(
                    Incident.project_id == target_incident.project_id,
                    Incident.id != target_incident.id,
                    IncidentReport.status == "done",
                    IncidentReport.embedding.is_not(None),
                )
                .order_by(dist_expr.asc(), IncidentReport.version.desc())
                .limit(limit * 4)
            )
            rows = (await self.db.execute(pg_stmt)).all()
            for cand_inc, cand_rep, sim_score in rows:
                if cand_inc.id in scored_matches:
                    continue
                score = round(float(sim_score), 4)
                if score >= threshold:
                    scored_matches[cand_inc.id] = {
                        "incident_id": cand_inc.id,
                        "similarity_score": score,
                        "status": cand_inc.status,
                        "severity": cand_inc.severity,
                        "started_at": cand_inc.started_at,
                        "ended_at": cand_inc.ended_at,
                        "summary": cand_rep.summary,
                        "root_cause": cand_rep.root_cause,
                        "suggested_fixes": cand_rep.suggested_fix,
                        "resolution_note": cand_inc.resolution_note,
                        "resolved_at": cand_inc.resolved_at,
                    }
        else:
            # Cross-dialect Python cosine calculation (SQLite tests)
            sqlite_stmt = (
                select(Incident, IncidentReport)
                .join(IncidentReport, Incident.id == IncidentReport.incident_id)
                .where(
                    Incident.project_id == target_incident.project_id,
                    Incident.id != target_incident.id,
                    IncidentReport.status == "done",
                    IncidentReport.embedding.is_not(None),
                )
                .order_by(IncidentReport.version.desc())
            )
            rows = (await self.db.execute(sqlite_stmt)).all()
            for cand_inc, cand_rep in rows:
                if cand_inc.id in scored_matches:
                    continue
                cand_vec = list(cand_rep.embedding) if cand_rep.embedding is not None else []
                sim = round(cosine_similarity(query_vector, cand_vec), 4)
                if sim >= threshold:
                    scored_matches[cand_inc.id] = {
                        "incident_id": cand_inc.id,
                        "similarity_score": sim,
                        "status": cand_inc.status,
                        "severity": cand_inc.severity,
                        "started_at": cand_inc.started_at,
                        "ended_at": cand_inc.ended_at,
                        "summary": cand_rep.summary,
                        "root_cause": cand_rep.root_cause,
                        "suggested_fixes": cand_rep.suggested_fix,
                        "resolution_note": cand_inc.resolution_note,
                        "resolved_at": cand_inc.resolved_at,
                    }

        ranked = sorted(
            scored_matches.values(),
            key=lambda m: m["similarity_score"],
            reverse=True,
        )
        return ranked[:limit]
