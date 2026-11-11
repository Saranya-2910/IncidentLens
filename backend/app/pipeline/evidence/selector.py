"""Evidence selector for building compact, redacted LLM context windows."""

import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.incident import Incident, IncidentPattern
from app.models.log_event import LogEvent
from app.pipeline.redaction.redactor import Redactor


@dataclass
class EvidenceLine:
    short_id: str
    event_id: int
    ts: str
    service: str
    level: str
    message: str


@dataclass
class EvidenceSelectionResult:
    lines: list[EvidenceLine]
    id_map: dict[str, int]
    formatted_block: str
    total_incident_events: int
    selected_count: int


class EvidenceSelector:
    """Selects a compact, high-signal, redacted set of log events for an incident."""

    def __init__(
        self,
        session: Session,
        max_lines: int = 45,
        max_chars: int = 12000,
    ):
        self.session = session
        self.max_lines = max_lines
        self.max_chars = max_chars

    def select_evidence(self, incident: Incident) -> EvidenceSelectionResult:
        """Gather pre-incident context, origin pattern samples, and top cascading pattern samples."""
        selected_by_id: dict[int, LogEvent] = {}

        # 0. Count total events in the incident/project window for reduction reporting
        total_stmt = (
            select(func.count(LogEvent.id))
            .where(LogEvent.project_id == incident.project_id)
        )
        total_events = self.session.execute(total_stmt).scalar_one()

        # 1. Pre-incident context: up to 5 lines right before incident.started_at
        pre_start = incident.started_at - timedelta(minutes=2)
        pre_stmt = (
            select(LogEvent)
            .where(
                LogEvent.project_id == incident.project_id,
                LogEvent.ts >= pre_start,
                LogEvent.ts < incident.started_at,
            )
            .order_by(LogEvent.ts.desc())
            .limit(5)
        )
        for evt in self.session.execute(pre_stmt).scalars().all():
            selected_by_id[evt.id] = evt

        # 2. Earliest origin lines (from origin_pattern_id or top candidate)
        origin_ids_to_query: list[uuid.UUID] = []
        if incident.origin_pattern_id:
            origin_ids_to_query.append(incident.origin_pattern_id)
        for cand in incident.origin_candidates[:2]:
            pid = uuid.UUID(str(cand["pattern_id"]))
            if pid not in origin_ids_to_query:
                origin_ids_to_query.append(pid)

        window_end = (incident.ended_at or incident.started_at) + timedelta(minutes=1)
        for pat_id in origin_ids_to_query:
            orig_stmt = (
                select(LogEvent)
                .where(
                    LogEvent.project_id == incident.project_id,
                    LogEvent.pattern_id == pat_id,
                    LogEvent.ts >= incident.started_at - timedelta(minutes=1),
                    LogEvent.ts <= window_end,
                )
                .order_by(LogEvent.ts.asc())
                .limit(6)
            )
            for evt in self.session.execute(orig_stmt).scalars().all():
                selected_by_id[evt.id] = evt

        # 3. Representative samples from all participating incident patterns (prioritized by count)
        assoc_stmt = (
            select(IncidentPattern)
            .where(IncidentPattern.incident_id == incident.id)
            .order_by(IncidentPattern.count.desc(), IncidentPattern.first_seen_in_incident.asc())
        )
        associations = list(self.session.execute(assoc_stmt).scalars().all())
        for assoc in associations:
            if len(selected_by_id) >= self.max_lines:
                break
            pat_stmt = (
                select(LogEvent)
                .where(
                    LogEvent.project_id == incident.project_id,
                    LogEvent.pattern_id == assoc.pattern_id,
                    LogEvent.ts >= incident.started_at - timedelta(minutes=1),
                    LogEvent.ts <= window_end,
                )
                .order_by(LogEvent.ts.asc())
                .limit(2)
            )
            for evt in self.session.execute(pat_stmt).scalars().all():
                selected_by_id[evt.id] = evt

        # 4. Sort chronologically and enforce max_lines / max_chars budget
        ordered_events = sorted(selected_by_id.values(), key=lambda e: (e.ts, e.id))
        if len(ordered_events) > self.max_lines:
            ordered_events = ordered_events[: self.max_lines]

        evidence_lines: list[EvidenceLine] = []
        id_map: dict[str, int] = {}
        formatted_rows: list[str] = []
        current_chars = 0

        for idx, evt in enumerate(ordered_events, start=1):
            short_id = f"L{idx}"
            redacted_msg = Redactor.redact(evt.message)
            # Keep stack traces compact if a single line is huge
            if len(redacted_msg) > 1200:
                redacted_msg = redacted_msg[:1150] + "\n... [truncated]"

            ts_str = evt.ts.isoformat()
            row_text = f"[{short_id}] {ts_str} [{evt.level}] [{evt.service}] {redacted_msg}"

            if current_chars + len(row_text) > self.max_chars and len(evidence_lines) >= 3:
                break

            evidence_lines.append(
                EvidenceLine(
                    short_id=short_id,
                    event_id=evt.id,
                    ts=ts_str,
                    service=evt.service,
                    level=evt.level,
                    message=redacted_msg,
                )
            )
            id_map[short_id] = evt.id
            formatted_rows.append(row_text)
            current_chars += len(row_text) + 1

        formatted_block = "\n".join(formatted_rows)
        return EvidenceSelectionResult(
            lines=evidence_lines,
            id_map=id_map,
            formatted_block=formatted_block,
            total_incident_events=total_events,
            selected_count=len(evidence_lines),
        )
